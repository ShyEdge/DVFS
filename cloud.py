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

# ANSI颜色代码
class Colors:
    """终端颜色控制"""
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    
    # 前景色
    BLACK = '\033[30m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    WHITE = '\033[37m'
    
    # 亮色
    BRIGHT_BLACK = '\033[90m'
    BRIGHT_RED = '\033[91m'
    BRIGHT_GREEN = '\033[92m'
    BRIGHT_YELLOW = '\033[93m'
    BRIGHT_BLUE = '\033[94m'
    BRIGHT_MAGENTA = '\033[95m'
    BRIGHT_CYAN = '\033[96m'
    BRIGHT_WHITE = '\033[97m'
    
    # 背景色
    BG_BLACK = '\033[40m'
    BG_RED = '\033[41m'
    BG_GREEN = '\033[42m'
    BG_YELLOW = '\033[43m'
    BG_BLUE = '\033[44m'
    BG_MAGENTA = '\033[45m'
    BG_CYAN = '\033[46m'
    BG_WHITE = '\033[47m'
    
    @staticmethod
    def disable():
        """禁用颜色（用于不支持ANSI的终端）"""
        Colors.RESET = ''
        Colors.BOLD = ''
        Colors.DIM = ''
        Colors.BLACK = Colors.RED = Colors.GREEN = Colors.YELLOW = ''
        Colors.BLUE = Colors.MAGENTA = Colors.CYAN = Colors.WHITE = ''
        Colors.BRIGHT_BLACK = Colors.BRIGHT_RED = Colors.BRIGHT_GREEN = ''
        Colors.BRIGHT_YELLOW = Colors.BRIGHT_BLUE = Colors.BRIGHT_MAGENTA = ''
        Colors.BRIGHT_CYAN = Colors.BRIGHT_WHITE = ''
        Colors.BG_BLACK = Colors.BG_RED = Colors.BG_GREEN = Colors.BG_YELLOW = ''
        Colors.BG_BLUE = Colors.BG_MAGENTA = Colors.BG_CYAN = Colors.BG_WHITE = ''

# 检测终端是否支持颜色
if not sys.stdout.isatty() or os.getenv('NO_COLOR'):
    Colors.disable()

# 配置
EDGE_HOST = '114.212.81.186'  # 边缘端IP地址
EDGE_PORT = 9999  # 边缘端DVFS服务端口
SSH_PORT = 15616  # SSH端口
SSH_USER = 'nvidia'  # SSH用户名
SSH_KEY_PATH = '~/.ssh/id_rsa_shy'  # SSH密钥路径
LOCAL_TUNNEL_PORT = 19999  # 本地隧道端口

# 全局变量，用于存储SSH隧道进程
_ssh_tunnel_process = None


def draw_progress_bar(percentage, width=40, color=Colors.CYAN):
    """绘制进度条
    
    Args:
        percentage: 百分比 (0.0-1.0)
        width: 进度条宽度
        color: 进度条颜色
    
    Returns:
        进度条字符串
    """
    filled = int(width * percentage)
    empty = width - filled
    
    bar = color + '█' * filled + Colors.DIM + '░' * empty + Colors.RESET
    percent_text = f"{percentage * 100:5.1f}%"
    
    return f"[{bar}] {Colors.BOLD}{percent_text}{Colors.RESET}"


def format_frequency(freq_hz, unit='auto'):
    """格式化频率显示
    
    Args:
        freq_hz: 频率（Hz）
        unit: 单位 ('auto', 'Hz', 'kHz', 'MHz', 'GHz')
    
    Returns:
        格式化的频率字符串
    """
    if freq_hz is None:
        return "N/A"
    
    if unit == 'auto':
        if freq_hz >= 1_000_000_000:
            return f"{freq_hz / 1_000_000_000:.2f} GHz"
        elif freq_hz >= 1_000_000:
            return f"{freq_hz / 1_000_000:.1f} MHz"
        elif freq_hz >= 1_000:
            return f"{freq_hz / 1_000:.1f} kHz"
        else:
            return f"{freq_hz} Hz"
    elif unit == 'GHz':
        return f"{freq_hz / 1_000_000_000:.2f} GHz"
    elif unit == 'MHz':
        return f"{freq_hz / 1_000_000:.1f} MHz"
    elif unit == 'kHz':
        return f"{freq_hz / 1_000:.1f} kHz"
    else:
        return f"{freq_hz} Hz"


def print_table_row(columns, widths, colors=None, separator='│'):
    """打印表格行
    
    Args:
        columns: 列内容列表
        widths: 每列宽度列表
        colors: 每列颜色列表（可选）
        separator: 列分隔符
    """
    if colors is None:
        colors = [Colors.RESET] * len(columns)
    
    row = separator
    for col, width, color in zip(columns, widths, colors):
        # 计算实际显示长度（去除ANSI颜色代码）
        display_len = len(col)
        for c in [Colors.RESET, Colors.BOLD, Colors.DIM, Colors.RED, Colors.GREEN, 
                  Colors.YELLOW, Colors.BLUE, Colors.MAGENTA, Colors.CYAN, Colors.WHITE,
                  Colors.BRIGHT_RED, Colors.BRIGHT_GREEN, Colors.BRIGHT_YELLOW,
                  Colors.BRIGHT_BLUE, Colors.BRIGHT_MAGENTA, Colors.BRIGHT_CYAN]:
            if c and c in col:
                display_len -= len(c)
        
        padding = width - display_len
        row += f" {color}{col}{Colors.RESET}{' ' * padding} {separator}"
    
    print(row)


def print_table_separator(widths, left='├', mid='┼', right='┤', line='─'):
    """打印表格分隔线"""
    parts = [left]
    for i, width in enumerate(widths):
        parts.append(line * (width + 2))
        if i < len(widths) - 1:
            parts.append(mid)
    parts.append(right)
    print(''.join(parts))


def print_box(title, content, color=Colors.CYAN):
    """打印边框盒子
    
    Args:
        title: 标题
        content: 内容列表（每个元素一行）
        color: 边框颜色
    """
    width = max(len(title), max(len(line) for line in content) if content else 0) + 4
    
    # 上边框
    print(f"{color}╔{'═' * width}╗{Colors.RESET}")
    # 标题
    print(f"{color}║{Colors.RESET} {Colors.BOLD}{title.center(width - 2)}{Colors.RESET} {color}║{Colors.RESET}")
    # 分隔线
    print(f"{color}╠{'═' * width}╣{Colors.RESET}")
    # 内容
    for line in content:
        padding = width - len(line) - 2
        print(f"{color}║{Colors.RESET} {line}{' ' * padding} {color}║{Colors.RESET}")
    # 下边框
    print(f"{color}╚{'═' * width}╝{Colors.RESET}")


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
            
            print(f"{Colors.DIM}正在连接到边缘端 {self.host}:{self.port}...{Colors.RESET}", end=' ')
            sock.connect((self.host, self.port))
            print(f"{Colors.GREEN}✓{Colors.RESET}")
            
            # 发送命令
            cmd_json = json.dumps(command)
            print(f"{Colors.DIM}发送命令: {cmd_json}{Colors.RESET}")
            sock.sendall(cmd_json.encode('utf-8'))
            
            # 接收响应
            response_data = sock.recv(8192).decode('utf-8')
            response = json.loads(response_data)
            
            status = response.get('status', 'unknown')
            if status == 'success':
                print(f"{Colors.DIM}收到响应: {Colors.GREEN}{status}{Colors.RESET}")
            else:
                print(f"{Colors.DIM}收到响应: {Colors.RED}{status}{Colors.RESET}")
            
            sock.close()
            return response
            
        except socket.timeout:
            print(f"\n{Colors.RED}✗ 错误: 连接超时 ({self.timeout}秒){Colors.RESET}")
            return {'status': 'error', 'message': '连接超时'}
        
        except ConnectionRefusedError:
            print(f"\n{Colors.RED}✗ 错误: 无法连接到 {self.host}:{self.port}{Colors.RESET}")
            print(f"{Colors.YELLOW}请确保边缘端服务正在运行 (运行 edge.py){Colors.RESET}")
            return {'status': 'error', 'message': '连接被拒绝'}
        
        except Exception as e:
            print(f"\n{Colors.RED}✗ 错误: {e}{Colors.RESET}")
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
    print(f"\n{Colors.BOLD}{Colors.BRIGHT_CYAN}╔{'═' * 78}╗{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BRIGHT_CYAN}║{' ' * 30}边缘端CPU状态{' ' * 32}║{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BRIGHT_CYAN}╚{'═' * 78}╝{Colors.RESET}\n")
    
    # 表头
    widths = [8, 18, 15, 15, 18]
    headers = ["CPU", "当前频率", "频率档位", "调频策略", "频率范围"]
    
    # 打印表头
    print(f"{Colors.BOLD}┌{'─' * (sum(widths) + len(widths) * 3 + 1)}┐{Colors.RESET}")
    colors = [Colors.BOLD + Colors.BRIGHT_YELLOW] * len(headers)
    print_table_row(headers, widths, colors, '│')
    print(f"{Colors.BOLD}├{'─' * (sum(widths) + len(widths) * 3 + 1)}┤{Colors.RESET}")
    
    # 打印每个CPU的信息
    for cpu_name, info in sorted(status_info.items()):
        current_freq = info.get('current_freq')
        governor = info.get('governor', 'N/A')
        available_freqs = info.get('available_freqs', [])
        
        # CPU名称
        cpu_display = f"{Colors.BRIGHT_CYAN}{cpu_name.upper()}{Colors.RESET}"
        
        # 当前频率
        if current_freq:
            freq_display = f"{Colors.BRIGHT_GREEN}{format_frequency(current_freq * 1000, 'MHz')}{Colors.RESET}"
        else:
            freq_display = f"{Colors.DIM}N/A{Colors.RESET}"
        
        # 频率档位和进度条
        if available_freqs and current_freq:
            num_levels = len(available_freqs)
            # 计算当前频率在可用频率中的位置
            if current_freq in available_freqs:
                current_idx = available_freqs.index(current_freq)
            else:
                # 找最接近的
                current_idx = min(range(len(available_freqs)), 
                                  key=lambda i: abs(available_freqs[i] - current_freq))
            
            percentage = current_idx / (num_levels - 1) if num_levels > 1 else 0
            level_display = f"{current_idx + 1}/{num_levels}"
        else:
            percentage = 0
            level_display = "N/A"
        
        # 调频策略
        if governor == 'userspace':
            gov_color = Colors.GREEN
        elif governor in ['performance', 'ondemand']:
            gov_color = Colors.YELLOW
        else:
            gov_color = Colors.RESET
        gov_display = f"{gov_color}{governor}{Colors.RESET}"
        
        # 频率范围
        if available_freqs:
            min_freq = min(available_freqs)
            max_freq = max(available_freqs)
            range_display = f"{format_frequency(min_freq * 1000, 'MHz')}-{format_frequency(max_freq * 1000, 'MHz')}"
        else:
            range_display = "N/A"
        
        # 打印行
        columns = [cpu_display, freq_display, level_display, gov_display, range_display]
        print_table_row(columns, widths, separator='│')
        
        # 打印进度条（如果有可用频率）
        if available_freqs and current_freq:
            bar = draw_progress_bar(percentage, width=60, 
                                    color=Colors.BRIGHT_GREEN if percentage > 0.6 else Colors.BRIGHT_YELLOW if percentage > 0.3 else Colors.BRIGHT_BLUE)
            print(f"│ {' ' * widths[0]}  {bar}  │")
    
    print(f"{Colors.BOLD}└{'─' * (sum(widths) + len(widths) * 3 + 1)}┘{Colors.RESET}\n")


def print_gpu_status(gpu_info):
    """美化打印GPU状态信息"""
    print(f"\n{Colors.BOLD}{Colors.BRIGHT_MAGENTA}╔{'═' * 78}╗{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BRIGHT_MAGENTA}║{' ' * 30}边缘端GPU状态{' ' * 32}║{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BRIGHT_MAGENTA}╚{'═' * 78}╝{Colors.RESET}\n")
    
    current_freq = gpu_info.get('current_freq')
    governor = gpu_info.get('governor', 'N/A')
    available_freqs = gpu_info.get('available_freqs', [])
    path = gpu_info.get('path', 'N/A')
    
    # 表头
    widths = [20, 18, 15, 20]
    headers = ["当前频率", "频率档位", "调频策略", "频率范围"]
    
    # 打印表头
    print(f"{Colors.BOLD}┌{'─' * (sum(widths) + len(widths) * 3 + 1)}┐{Colors.RESET}")
    colors = [Colors.BOLD + Colors.BRIGHT_YELLOW] * len(headers)
    print_table_row(headers, widths, colors, '│')
    print(f"{Colors.BOLD}├{'─' * (sum(widths) + len(widths) * 3 + 1)}┤{Colors.RESET}")
    
    # 当前频率
    if current_freq:
        freq_display = f"{Colors.BRIGHT_GREEN}{format_frequency(current_freq, 'MHz')}{Colors.RESET}"
    else:
        freq_display = f"{Colors.DIM}N/A{Colors.RESET}"
    
    # 频率档位和进度条
    if available_freqs and current_freq:
        num_levels = len(available_freqs)
        # 计算当前频率在可用频率中的位置
        if current_freq in available_freqs:
            current_idx = available_freqs.index(current_freq)
        else:
            # 找最接近的
            current_idx = min(range(len(available_freqs)), 
                              key=lambda i: abs(available_freqs[i] - current_freq))
        
        percentage = current_idx / (num_levels - 1) if num_levels > 1 else 0
        level_display = f"{current_idx + 1}/{num_levels}"
    else:
        percentage = 0
        level_display = "N/A"
    
    # 调频策略
    if governor == 'userspace':
        gov_color = Colors.GREEN
    elif governor in ['performance', 'simple_ondemand']:
        gov_color = Colors.YELLOW
    else:
        gov_color = Colors.RESET
    gov_display = f"{gov_color}{governor}{Colors.RESET}"
    
    # 频率范围
    if available_freqs:
        min_freq = min(available_freqs)
        max_freq = max(available_freqs)
        range_display = f"{format_frequency(min_freq, 'MHz')}-{format_frequency(max_freq, 'MHz')}"
    else:
        range_display = "N/A"
    
    # 打印数据行
    columns = [freq_display, level_display, gov_display, range_display]
    print_table_row(columns, widths, separator='│')
    
    # 打印进度条（如果有可用频率）
    if available_freqs and current_freq:
        bar = draw_progress_bar(percentage, width=60, 
                                color=Colors.BRIGHT_GREEN if percentage > 0.6 else Colors.BRIGHT_YELLOW if percentage > 0.3 else Colors.BRIGHT_BLUE)
        print(f"│ {bar}  │")
    
    print(f"{Colors.BOLD}└{'─' * (sum(widths) + len(widths) * 3 + 1)}┘{Colors.RESET}")
    
    # 控制路径信息
    if path and path != 'N/A':
        print(f"\n{Colors.DIM}控制路径: {path}{Colors.RESET}\n")
    else:
        print()


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
    
    # 打印欢迎横幅
    print(f"\n{Colors.BOLD}{Colors.BRIGHT_CYAN}╔{'═' * 78}╗{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BRIGHT_CYAN}║{' ' * 28}云端DVFS控制工具{' ' * 31}║{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BRIGHT_CYAN}║{' ' * 20}Dynamic Voltage and Frequency Scaling{' ' * 20}║{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BRIGHT_CYAN}╚{'═' * 78}╝{Colors.RESET}")
    
    # 如果使用SSH隧道
    if args.use_tunnel:
        print(f"\n{Colors.BOLD}{Colors.BRIGHT_YELLOW}>>> 使用SSH隧道模式{Colors.RESET}")
        print(f"{Colors.DIM}{'─' * 78}{Colors.RESET}")
        
        if not setup_ssh_tunnel(
            remote_host=args.host,
            remote_port=args.port,
            local_port=args.local_port,
            ssh_key=args.ssh_key,
            ssh_port=args.ssh_port,
            ssh_user=args.ssh_user
        ):
            print(f"{Colors.RED}SSH隧道建立失败，退出{Colors.RESET}")
            sys.exit(1)
        
        # 使用localhost和本地隧道端口
        print(f"\n{Colors.GREEN}✓ 隧道已建立{Colors.RESET}")
        print(f"{Colors.DIM}通过 localhost:{args.local_port} 连接到边缘端{Colors.RESET}")
        client = CloudDVFSClient(host='localhost', port=args.local_port, timeout=args.timeout)
        print(f"{Colors.CYAN}目标边缘端: {args.ssh_user}@{args.host}:{args.port} (via SSH tunnel){Colors.RESET}\n")
    else:
        # 直接连接
        print(f"\n{Colors.BRIGHT_YELLOW}>>> 直接连接模式{Colors.RESET}")
        client = CloudDVFSClient(host=args.host, port=args.port, timeout=args.timeout)
        print(f"{Colors.CYAN}目标边缘端: {args.host}:{args.port}{Colors.RESET}\n")
    
    # 交互模式
    if args.interactive:
        interactive_mode(client)
        return
    
    # 执行单个命令
    if args.status:
        print(f"{Colors.DIM}正在查询边缘端状态...{Colors.RESET}")
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
            print(f"{Colors.RED}✗ 错误: {response.get('message', '未知错误')}{Colors.RESET}")
    
    elif args.governor:
        print(f"{Colors.DIM}正在设置调频策略...{Colors.RESET}")
        response = client.set_governor(args.governor, args.cpu, target=args.target)
        if response['status'] == 'success':
            print(f"\n{Colors.GREEN}✓ {response.get('message', response['status'])}{Colors.RESET}\n")
        else:
            print(f"\n{Colors.RED}✗ {response.get('message', response['status'])}{Colors.RESET}\n")
    
    elif args.freq is not None:
        print(f"{Colors.DIM}正在设置频率...{Colors.RESET}")
        response = client.set_frequency(args.freq, args.cpu, target=args.target)
        if response['status'] == 'success':
            print(f"\n{Colors.GREEN}✓ {response.get('message', '成功')}{Colors.RESET}")
            if 'current_status' in response:
                print_cpu_status(response['current_status'])
            elif 'gpu_status' in response:
                print_gpu_status(response['gpu_status'])
        else:
            print(f"\n{Colors.RED}✗ 错误: {response.get('message', '未知错误')}{Colors.RESET}\n")
    
    else:
        parser.print_help()


def print_interactive_help():
    """打印交互模式帮助"""
    print(f"\n{Colors.BOLD}{Colors.BRIGHT_CYAN}╔{'═' * 78}╗{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BRIGHT_CYAN}║{' ' * 28}DVFS 交互模式帮助{' ' * 29}║{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BRIGHT_CYAN}╚{'═' * 78}╝{Colors.RESET}\n")
    
    commands = [
        ("status [target]", "查询边缘端状态", "cpu, gpu, all"),
        ("freq <频率> [target]", "设置频率", "0.0-1.0 或具体频率值"),
        ("freq <频率> <CPU编号>", "设置指定CPU频率", "仅适用于CPU"),
        ("governor <策略> [target]", "设置调频策略", "userspace, performance等"),
        ("menu", "显示快捷菜单", ""),
        ("help", "显示此帮助", ""),
        ("quit/exit", "退出交互模式", ""),
    ]
    
    # 打印命令列表
    widths = [25, 25, 25]
    headers = ["命令", "说明", "参数说明"]
    
    print(f"{Colors.BOLD}┌{'─' * (sum(widths) + len(widths) * 3 + 1)}┐{Colors.RESET}")
    colors = [Colors.BOLD + Colors.BRIGHT_YELLOW] * len(headers)
    print_table_row(headers, widths, colors, '│')
    print(f"{Colors.BOLD}├{'─' * (sum(widths) + len(widths) * 3 + 1)}┤{Colors.RESET}")
    
    for i, (cmd, desc, params) in enumerate(commands):
        colors = [Colors.BRIGHT_GREEN, Colors.RESET, Colors.DIM]
        print_table_row([cmd, desc, params], widths, colors, '│')
    
    print(f"{Colors.BOLD}└{'─' * (sum(widths) + len(widths) * 3 + 1)}┘{Colors.RESET}\n")
    
    # 打印示例
    print(f"{Colors.BOLD}{Colors.BRIGHT_YELLOW}常用示例:{Colors.RESET}")
    examples = [
        ("status", "查询CPU状态"),
        ("status gpu", "查询GPU状态"),
        ("status all", "查询所有状态"),
        ("freq 0.5", "设置CPU频率到50%"),
        ("freq 0.8 gpu", "设置GPU频率到80%"),
        ("freq 0.8 0", "设置CPU0到80%"),
        ("governor userspace", "设置CPU调频策略"),
    ]
    
    for cmd, desc in examples:
        print(f"  {Colors.BRIGHT_CYAN}{cmd:25s}{Colors.RESET} {Colors.DIM}- {desc}{Colors.RESET}")
    print()


def print_interactive_menu():
    """打印交互菜单"""
    print(f"\n{Colors.BOLD}{Colors.BRIGHT_GREEN}╔{'═' * 78}╗{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BRIGHT_GREEN}║{' ' * 28}快捷操作菜单{' ' * 33}║{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BRIGHT_GREEN}╚{'═' * 78}╝{Colors.RESET}\n")
    
    menu_items = [
        ("1", "查询CPU状态", "status", Colors.CYAN),
        ("2", "查询GPU状态", "status gpu", Colors.MAGENTA),
        ("3", "查询所有状态", "status all", Colors.BRIGHT_CYAN),
        ("4", "设置CPU频率(低)", "freq 0.2", Colors.BLUE),
        ("5", "设置CPU频率(中)", "freq 0.5", Colors.YELLOW),
        ("6", "设置CPU频率(高)", "freq 0.8", Colors.BRIGHT_YELLOW),
        ("7", "设置GPU频率(低)", "freq 0.2 gpu", Colors.BLUE),
        ("8", "设置GPU频率(中)", "freq 0.5 gpu", Colors.YELLOW),
        ("9", "设置GPU频率(高)", "freq 0.8 gpu", Colors.BRIGHT_YELLOW),
        ("0", "返回命令行模式", "", Colors.RESET),
    ]
    
    # 打印菜单项
    widths = [8, 25, 30]
    headers = ["编号", "操作", "对应命令"]
    
    print(f"{Colors.BOLD}┌{'─' * (sum(widths) + len(widths) * 3 + 1)}┐{Colors.RESET}")
    colors = [Colors.BOLD + Colors.BRIGHT_YELLOW] * len(headers)
    print_table_row(headers, widths, colors, '│')
    print(f"{Colors.BOLD}├{'─' * (sum(widths) + len(widths) * 3 + 1)}┤{Colors.RESET}")
    
    for num, desc, cmd, color in menu_items:
        colors = [Colors.BOLD + color, Colors.RESET, Colors.DIM]
        print_table_row([num, desc, cmd], widths, colors, '│')
    
    print(f"{Colors.BOLD}└{'─' * (sum(widths) + len(widths) * 3 + 1)}┘{Colors.RESET}\n")


def interactive_mode(client):
    """交互模式"""
    print(f"\n{Colors.BOLD}{Colors.BRIGHT_GREEN}{'=' * 80}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BRIGHT_GREEN}进入交互模式{Colors.RESET}")
    print(f"{Colors.BRIGHT_YELLOW}提示: 输入 'menu' 查看快捷菜单, 'help' 查看完整帮助, 'quit' 退出{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BRIGHT_GREEN}{'=' * 80}{Colors.RESET}\n")
    
    while True:
        try:
            # 显示提示符
            prompt = f"{Colors.BOLD}{Colors.BRIGHT_CYAN}DVFS>{Colors.RESET} "
            cmd = input(prompt).strip()
            
            if not cmd:
                continue
            
            if cmd.lower() in ['quit', 'exit', 'q']:
                print(f"\n{Colors.BRIGHT_GREEN}退出交互模式{Colors.RESET}")
                break
            
            if cmd.lower() == 'help':
                print_interactive_help()
                continue
            
            if cmd.lower() == 'menu':
                print_interactive_menu()
                # 等待用户选择
                choice = input(f"\n{Colors.BRIGHT_YELLOW}请选择操作 (0-9 或按Enter跳过):{Colors.RESET} ").strip()
                
                if choice == '1':
                    cmd = 'status'
                elif choice == '2':
                    cmd = 'status gpu'
                elif choice == '3':
                    cmd = 'status all'
                elif choice == '4':
                    cmd = 'freq 0.2'
                elif choice == '5':
                    cmd = 'freq 0.5'
                elif choice == '6':
                    cmd = 'freq 0.8'
                elif choice == '7':
                    cmd = 'freq 0.2 gpu'
                elif choice == '8':
                    cmd = 'freq 0.5 gpu'
                elif choice == '9':
                    cmd = 'freq 0.8 gpu'
                elif choice == '0' or not choice:
                    continue
                else:
                    print(f"{Colors.RED}无效的选择{Colors.RESET}")
                    continue
                
                print(f"{Colors.DIM}执行: {cmd}{Colors.RESET}")
            
            parts = cmd.split()
            
            if parts[0] == 'status':
                target = parts[1] if len(parts) >= 2 else 'cpu'
                print(f"{Colors.DIM}正在查询{target.upper()}状态...{Colors.RESET}")
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
                    print(f"{Colors.RED}✗ 错误: {response.get('message', '未知错误')}{Colors.RESET}")
            
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
                
                print(f"{Colors.DIM}正在设置频率...{Colors.RESET}")
                response = client.set_frequency(freq, cpu, target=target)
                if response['status'] == 'success':
                    print(f"{Colors.GREEN}✓ {response.get('message', '成功')}{Colors.RESET}")
                    # 显示状态
                    if 'current_status' in response:
                        print_cpu_status(response['current_status'])
                    elif 'gpu_status' in response:
                        print_gpu_status(response['gpu_status'])
                else:
                    print(f"{Colors.RED}✗ {response.get('message', response['status'])}{Colors.RESET}")
            
            elif parts[0] == 'governor' and len(parts) >= 2:
                governor = parts[1]
                target = parts[2] if len(parts) >= 3 else 'cpu'
                print(f"{Colors.DIM}正在设置调频策略...{Colors.RESET}")
                response = client.set_governor(governor, target=target)
                if response['status'] == 'success':
                    print(f"{Colors.GREEN}✓ {response.get('message', response['status'])}{Colors.RESET}")
                else:
                    print(f"{Colors.RED}✗ {response.get('message', response['status'])}{Colors.RESET}")
            
            else:
                print(f"{Colors.RED}未知命令: {parts[0]}{Colors.RESET}")
                print(f"{Colors.YELLOW}输入 'help' 查看帮助 或 'menu' 查看快捷菜单{Colors.RESET}")
        
        except KeyboardInterrupt:
            print(f"\n\n{Colors.BRIGHT_GREEN}退出交互模式{Colors.RESET}")
            break
        except ValueError as e:
            print(f"{Colors.RED}参数错误: {e}{Colors.RESET}")
        except Exception as e:
            print(f"{Colors.RED}错误: {e}{Colors.RESET}")


if __name__ == '__main__':
    main()

