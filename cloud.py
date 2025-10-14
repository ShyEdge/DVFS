#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
云端DVFS控制脚本
向边缘端发送调频命令
"""

import socket
import json
import argparse
import sys
import subprocess
import time
import os
import signal
import atexit
from datetime import datetime

# 配置
EDGE_HOST = '114.212.81.186'  # 边缘端IP地址
EDGE_PORT = 9999  # 边缘端DVFS服务端口
SSH_PORT = 15616  # SSH端口
SSH_USER = 'nvidia'  # SSH用户名
SSH_KEY_PATH = '~/shy/id_rsa_shy'  # SSH密钥路径
LOCAL_TUNNEL_PORT = 19999  # 本地隧道端口

# 全局变量，用于存储SSH隧道进程
_ssh_tunnel_process = None


def cleanup_tunnel():
    """清理SSH隧道"""
    global _ssh_tunnel_process
    if _ssh_tunnel_process is not None:
        try:
            print("\n正在关闭SSH隧道...")
            _ssh_tunnel_process.terminate()
            _ssh_tunnel_process.wait(timeout=3)
            print("SSH隧道已关闭")
        except:
            try:
                _ssh_tunnel_process.kill()
            except:
                pass
        _ssh_tunnel_process = None


def setup_ssh_tunnel(remote_host=EDGE_HOST, remote_port=EDGE_PORT, 
                     local_port=LOCAL_TUNNEL_PORT, ssh_key=SSH_KEY_PATH, 
                     ssh_port=SSH_PORT, ssh_user=SSH_USER):
    """建立SSH隧道
    
    Args:
        remote_host: 远程主机名或IP
        remote_port: 远程DVFS服务端口
        local_port: 本地隧道端口
        ssh_key: SSH密钥路径
        ssh_port: SSH连接端口
        ssh_user: SSH用户名
    
    Returns:
        成功返回True，失败返回False
    """
    global _ssh_tunnel_process
    
    # 展开用户目录
    ssh_key = os.path.expanduser(ssh_key)
    
    # 检查SSH密钥是否存在
    if not os.path.exists(ssh_key):
        print(f"警告: SSH密钥不存在: {ssh_key}")
        print("将尝试使用默认SSH配置")
        ssh_key = None
    
    # 构建SSH命令
    ssh_cmd = ['ssh', '-N', '-L', f'{local_port}:localhost:{remote_port}']
    
    # 添加SSH端口
    ssh_cmd.extend(['-p', str(ssh_port)])
    
    if ssh_key:
        ssh_cmd.extend(['-i', ssh_key])
    
    # 添加其他SSH选项
    ssh_cmd.extend([
        '-o', 'StrictHostKeyChecking=no',
        '-o', 'UserKnownHostsFile=/dev/null',
        '-o', 'ServerAliveInterval=60',
        '-o', 'ExitOnForwardFailure=yes',
        f'{ssh_user}@{remote_host}'
    ])
    
    print(f"建立SSH隧道: localhost:{local_port} -> {ssh_user}@{remote_host}:{remote_port} (SSH端口: {ssh_port})")
    print(f"SSH命令: ssh -p {ssh_port} -L {local_port}:localhost:{remote_port} {ssh_user}@{remote_host} ...")
    
    try:
        # 启动SSH隧道
        _ssh_tunnel_process = subprocess.Popen(
            ssh_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL
        )
        
        # 等待隧道建立
        print("等待隧道建立", end='', flush=True)
        for i in range(15):  # 等待最多3秒
            time.sleep(0.2)
            print('.', end='', flush=True)
            
            # 检查进程是否还在运行
            if _ssh_tunnel_process.poll() is not None:
                # 进程已退出，读取错误信息
                _, stderr = _ssh_tunnel_process.communicate()
                print("\n错误: SSH隧道建立失败")
                if stderr:
                    print(f"错误信息: {stderr.decode('utf-8', errors='ignore')}")
                _ssh_tunnel_process = None
                return False
            
            # 尝试连接本地端口检查隧道是否就绪
            try:
                test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                test_sock.settimeout(0.1)
                test_sock.connect(('localhost', local_port))
                test_sock.close()
                print(" 成功!")
                
                # 注册清理函数
                atexit.register(cleanup_tunnel)
                return True
            except:
                pass
        
        print(" 超时!")
        print("警告: 隧道可能未完全建立，但会继续尝试连接")
        atexit.register(cleanup_tunnel)
        return True
        
    except Exception as e:
        print(f"\n错误: 无法建立SSH隧道: {e}")
        _ssh_tunnel_process = None
        return False


class CloudDVFSClient:
    """云端DVFS客户端"""
    
    def __init__(self, host=EDGE_HOST, port=EDGE_PORT, timeout=10):
        self.host = host
        self.port = port
        self.timeout = timeout
    
    def send_command(self, command):
        """发送命令到边缘端
        
        Args:
            command: 命令字典
        
        Returns:
            响应字典
        """
        try:
            # 创建socket连接
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)
            
            print(f"正在连接到边缘端 {self.host}:{self.port}...")
            sock.connect((self.host, self.port))
            print("连接成功！")
            
            # 发送命令
            cmd_json = json.dumps(command)
            print(f"发送命令: {cmd_json}")
            sock.sendall(cmd_json.encode('utf-8'))
            
            # 接收响应
            response_data = sock.recv(8192).decode('utf-8')
            response = json.loads(response_data)
            
            print(f"收到响应: {response.get('status', 'unknown')}")
            
            sock.close()
            return response
            
        except socket.timeout:
            print(f"错误: 连接超时 ({self.timeout}秒)")
            return {'status': 'error', 'message': '连接超时'}
        
        except ConnectionRefusedError:
            print(f"错误: 无法连接到 {self.host}:{self.port}")
            print("请确保边缘端服务正在运行 (运行 edge.py)")
            return {'status': 'error', 'message': '连接被拒绝'}
        
        except Exception as e:
            print(f"错误: {e}")
            return {'status': 'error', 'message': str(e)}
    
    def set_frequency(self, frequency, cpu=None, target='cpu'):
        """设置CPU或GPU频率
        
        Args:
            frequency: 目标频率(kHz/Hz)或0-1之间的频率索引比例
            cpu: CPU核心编号，None表示所有核心（仅CPU时有效）
            target: 'cpu' 或 'gpu'
        """
        command = {
            'action': 'set_frequency',
            'frequency': frequency,
            'target': target,
            'timestamp': datetime.now().isoformat()
        }
        
        if cpu is not None and target == 'cpu':
            command['cpu'] = cpu
        
        response = self.send_command(command)
        return response
    
    def get_status(self, target='cpu'):
        """获取边缘端CPU或GPU状态
        
        Args:
            target: 'cpu', 'gpu' 或 'all'
        """
        command = {
            'action': 'get_status',
            'target': target,
            'timestamp': datetime.now().isoformat()
        }
        
        response = self.send_command(command)
        return response
    
    def set_governor(self, governor='userspace', cpu=None, target='cpu'):
        """设置调频策略
        
        Args:
            governor: 调频策略名称
            cpu: CPU核心编号，None表示所有核心（仅CPU时有效）
            target: 'cpu' 或 'gpu'
        """
        command = {
            'action': 'set_governor',
            'governor': governor,
            'target': target,
            'timestamp': datetime.now().isoformat()
        }
        
        if cpu is not None and target == 'cpu':
            command['cpu'] = cpu
        
        response = self.send_command(command)
        return response


def print_cpu_status(status_info):
    """美化打印CPU状态信息"""
    print("\n" + "=" * 60)
    print("边缘端CPU状态")
    print("=" * 60)
    
    for cpu_name, info in sorted(status_info.items()):
        print(f"\n{cpu_name.upper()}:")
        if info['current_freq']:
            print(f"  当前频率: {info['current_freq']} kHz ({info['current_freq']/1000:.1f} MHz)")
        else:
            print(f"  当前频率: N/A")
        print(f"  调频策略: {info['governor']}")
        
        if info['available_freqs']:
            freqs = info['available_freqs']
            print(f"  可用频率: {len(freqs)} 档")
            print(f"    最低: {min(freqs)} kHz ({min(freqs)/1000:.1f} MHz)")
            print(f"    最高: {max(freqs)} kHz ({max(freqs)/1000:.1f} MHz)")
    
    print("=" * 60 + "\n")


def print_gpu_status(gpu_info):
    """美化打印GPU状态信息"""
    print("\n" + "=" * 60)
    print("边缘端GPU状态")
    print("=" * 60)
    
    print("\nGPU:")
    if gpu_info.get('current_freq'):
        freq_mhz = gpu_info['current_freq'] / 1000000
        print(f"  当前频率: {gpu_info['current_freq']} Hz ({freq_mhz:.1f} MHz)")
    else:
        print(f"  当前频率: N/A")
    
    print(f"  调频策略: {gpu_info.get('governor', 'N/A')}")
    
    if gpu_info.get('available_freqs'):
        freqs = gpu_info['available_freqs']
        print(f"  可用频率: {len(freqs)} 档")
        min_freq_mhz = min(freqs) / 1000000
        max_freq_mhz = max(freqs) / 1000000
        print(f"    最低: {min(freqs)} Hz ({min_freq_mhz:.1f} MHz)")
        print(f"    最高: {max(freqs)} Hz ({max_freq_mhz:.1f} MHz)")
    
    if gpu_info.get('path'):
        print(f"  控制路径: {gpu_info['path']}")
    
    print("=" * 60 + "\n")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description='云端DVFS控制工具 - 向边缘端发送调频命令',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 查询CPU和GPU状态
  python3 cloud.py --use-tunnel --status --target all
  
  # 查询GPU状态
  python3 cloud.py --use-tunnel --status --target gpu
  
  # 设置CPU频率到50%
  python3 cloud.py --use-tunnel --freq 0.5
  
  # 设置GPU频率到80%
  python3 cloud.py --use-tunnel --freq 0.8 --target gpu
  
  # 设置CPU调频策略为userspace
  python3 cloud.py --use-tunnel --governor userspace
  
  # 设置GPU调频策略为userspace
  python3 cloud.py --use-tunnel --governor userspace --target gpu
  
  # 设置CPU0的频率
  python3 cloud.py --use-tunnel --freq 0.8 --cpu 0
  
  # 交互模式（推荐）
  python3 cloud.py --use-tunnel --interactive
        """
    )
    
    parser.add_argument('--host', type=str, default=EDGE_HOST,
                        help=f'边缘端IP地址 (默认: {EDGE_HOST})')
    parser.add_argument('--port', type=int, default=EDGE_PORT,
                        help=f'边缘端端口 (默认: {EDGE_PORT})')
    parser.add_argument('--timeout', type=int, default=10,
                        help='连接超时时间(秒) (默认: 10)')
    
    parser.add_argument('--use-tunnel', '--tunnel', action='store_true',
                        help='使用SSH隧道连接（推荐，适用于网络隔离场景）')
    parser.add_argument('--ssh-user', type=str, default=SSH_USER,
                        help=f'SSH用户名 (默认: {SSH_USER})')
    parser.add_argument('--ssh-key', type=str, default=SSH_KEY_PATH,
                        help=f'SSH密钥路径 (默认: {SSH_KEY_PATH})')
    parser.add_argument('--ssh-port', type=int, default=SSH_PORT,
                        help=f'SSH连接端口 (默认: {SSH_PORT})')
    parser.add_argument('--local-port', type=int, default=LOCAL_TUNNEL_PORT,
                        help=f'SSH隧道本地端口 (默认: {LOCAL_TUNNEL_PORT})')
    
    parser.add_argument('--freq', '--frequency', type=float,
                        help='目标频率(kHz/Hz)或频率索引(0.0-1.0)')
    parser.add_argument('--cpu', type=int,
                        help='指定CPU核心编号，不指定则应用到所有核心')
    parser.add_argument('--target', type=str, default='cpu', choices=['cpu', 'gpu', 'all'],
                        help='控制目标：cpu, gpu 或 all (默认: cpu)')
    parser.add_argument('--governor', type=str,
                        help='设置调频策略 (如: userspace, performance, powersave)')
    parser.add_argument('--status', action='store_true',
                        help='查询边缘端状态')
    parser.add_argument('--interactive', '-i', action='store_true',
                        help='进入交互模式')
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("云端DVFS控制工具")
    print("=" * 60)
    
    # 如果使用SSH隧道
    if args.use_tunnel:
        print("\n>>> 使用SSH隧道模式")
        print("-" * 60)
        
        if not setup_ssh_tunnel(
            remote_host=args.host,
            remote_port=args.port,
            local_port=args.local_port,
            ssh_key=args.ssh_key,
            ssh_port=args.ssh_port,
            ssh_user=args.ssh_user
        ):
            print("SSH隧道建立失败，退出")
            sys.exit(1)
        
        # 使用localhost和本地隧道端口
        print(f"\n隧道已建立，通过 localhost:{args.local_port} 连接到边缘端")
        client = CloudDVFSClient(host='localhost', port=args.local_port, timeout=args.timeout)
        print(f"目标边缘端: {args.ssh_user}@{args.host}:{args.port} (via SSH tunnel)\n")
    else:
        # 直接连接
        client = CloudDVFSClient(host=args.host, port=args.port, timeout=args.timeout)
        print(f"目标边缘端: {args.host}:{args.port}\n")
    
    # 交互模式
    if args.interactive:
        print("进入交互模式 (输入 'help' 查看帮助, 'quit' 退出)")
        interactive_mode(client)
        return
    
    # 执行单个命令
    if args.status:
        response = client.get_status(target=args.target)
        if response['status'] == 'success':
            if args.target == 'all':
                if 'cpu_status' in response:
                    print_cpu_status(response['cpu_status'])
                if 'gpu_status' in response:
                    print_gpu_status(response['gpu_status'])
            elif args.target == 'gpu':
                if 'gpu_status' in response:
                    print_gpu_status(response['gpu_status'])
            else:  # cpu
                if 'status_info' in response:
                    print_cpu_status(response['status_info'])
        else:
            print(f"错误: {response.get('message', '未知错误')}")
    
    elif args.governor:
        response = client.set_governor(args.governor, args.cpu, target=args.target)
        print(f"\n结果: {response.get('message', response['status'])}\n")
    
    elif args.freq is not None:
        response = client.set_frequency(args.freq, args.cpu, target=args.target)
        if response['status'] == 'success':
            print(f"\n结果: {response.get('message', '成功')}\n")
            if 'current_status' in response:
                print_cpu_status(response['current_status'])
            elif 'gpu_status' in response:
                print_gpu_status(response['gpu_status'])
        else:
            print(f"\n错误: {response.get('message', '未知错误')}\n")
    
    else:
        parser.print_help()


def interactive_mode(client):
    """交互模式"""
    while True:
        try:
            cmd = input("\nDVFS> ").strip()
            
            if not cmd:
                continue
            
            if cmd.lower() in ['quit', 'exit', 'q']:
                print("退出交互模式")
                break
            
            if cmd.lower() == 'help':
                print("""
可用命令:
  status [target]              - 查询边缘端状态 (target: cpu/gpu/all，默认cpu)
  freq <频率> [target]         - 设置频率 (kHz/Hz或0.0-1.0的索引)
  freq <频率> <CPU编号>        - 设置指定CPU的频率
  governor <策略> [target]     - 设置调频策略 (target: cpu/gpu，默认cpu)
  help                         - 显示此帮助
  quit                         - 退出

示例:
  status                    - 查询CPU状态
  status gpu                - 查询GPU状态
  status all                - 查询所有状态
  freq 0.5                  - 设置CPU频率到50%
  freq 0.8 gpu              - 设置GPU频率到80%
  freq 1200000              - 设置CPU到指定频率
  freq 0.8 0                - 设置CPU0到80%
  governor userspace        - 设置CPU调频策略
  governor userspace gpu    - 设置GPU调频策略
                """)
                continue
            
            parts = cmd.split()
            
            if parts[0] == 'status':
                target = parts[1] if len(parts) >= 2 else 'cpu'
                response = client.get_status(target=target)
                if response['status'] == 'success':
                    if target == 'all':
                        if 'cpu_status' in response:
                            print_cpu_status(response['cpu_status'])
                        if 'gpu_status' in response:
                            print_gpu_status(response['gpu_status'])
                    elif target == 'gpu':
                        if 'gpu_status' in response:
                            print_gpu_status(response['gpu_status'])
                    else:  # cpu
                        if 'status_info' in response:
                            print_cpu_status(response['status_info'])
                else:
                    print(f"错误: {response.get('message', '未知错误')}")
            
            elif parts[0] == 'freq' and len(parts) >= 2:
                freq = float(parts[1])
                # 判断第三个参数是target还是CPU编号
                if len(parts) >= 3:
                    if parts[2] in ['cpu', 'gpu']:
                        target = parts[2]
                        cpu = None
                    else:
                        target = 'cpu'
                        cpu = int(parts[2])
                else:
                    target = 'cpu'
                    cpu = None
                
                response = client.set_frequency(freq, cpu, target=target)
                print(f"结果: {response.get('message', response['status'])}")
            
            elif parts[0] == 'governor' and len(parts) >= 2:
                governor = parts[1]
                target = parts[2] if len(parts) >= 3 else 'cpu'
                response = client.set_governor(governor, target=target)
                print(f"结果: {response.get('message', response['status'])}")
            
            else:
                print("未知命令，输入 'help' 查看帮助")
        
        except KeyboardInterrupt:
            print("\n\n退出交互模式")
            break
        except Exception as e:
            print(f"错误: {e}")


if __name__ == '__main__':
    main()

