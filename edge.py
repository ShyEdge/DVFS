#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
边缘端DVFS服务
运行在Jetson TX2上，接收云端的调频命令并执行
"""

import socket
import json
import os
import sys
import subprocess
import logging
from datetime import datetime

# ANSI颜色代码
class Colors:
    """终端颜色控制"""
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    
    # 前景色
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    WHITE = '\033[37m'
    
    # 亮色
    BRIGHT_RED = '\033[91m'
    BRIGHT_GREEN = '\033[92m'
    BRIGHT_YELLOW = '\033[93m'
    BRIGHT_BLUE = '\033[94m'
    BRIGHT_MAGENTA = '\033[95m'
    BRIGHT_CYAN = '\033[96m'
    BRIGHT_WHITE = '\033[97m'
    
    @staticmethod
    def disable():
        """禁用颜色（用于不支持ANSI的终端）"""
        Colors.RESET = ''
        Colors.BOLD = ''
        Colors.DIM = ''
        Colors.RED = Colors.GREEN = Colors.YELLOW = ''
        Colors.BLUE = Colors.MAGENTA = Colors.CYAN = Colors.WHITE = ''
        Colors.BRIGHT_RED = Colors.BRIGHT_GREEN = Colors.BRIGHT_YELLOW = ''
        Colors.BRIGHT_BLUE = Colors.BRIGHT_MAGENTA = Colors.BRIGHT_CYAN = ''
        Colors.BRIGHT_WHITE = ''

# 检测终端是否支持颜色
if not sys.stdout.isatty() or os.getenv('NO_COLOR'):
    Colors.disable()

# 配置
HOST = '0.0.0.0'
PORT = 9999
LOG_FILE = '/tmp/dvfs_edge.log'

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)

class CPUController:
    """CPU频率控制器"""
    
    def __init__(self):
        self.cpu_base_path = '/sys/devices/system/cpu'
        self.available_cpus = self.get_available_cpus()
        logging.info(f"初始化CPU控制器，可用CPU: {self.available_cpus}")
        
    def get_available_cpus(self):
        """获取所有可用的CPU核心"""
        cpus = []
        cpu_dirs = os.listdir(self.cpu_base_path)
        for cpu_dir in cpu_dirs:
            if cpu_dir.startswith('cpu') and cpu_dir[3:].isdigit():
                cpus.append(int(cpu_dir[3:]))
        return sorted(cpus)
    
    def get_available_frequencies(self, cpu=0):
        """获取指定CPU的可用频率列表"""
        try:
            freq_path = f'{self.cpu_base_path}/cpu{cpu}/cpufreq/scaling_available_frequencies'
            with open(freq_path, 'r') as f:
                freqs = [int(x) for x in f.read().strip().split()]
            return freqs
        except Exception as e:
            logging.error(f"读取可用频率失败: {e}")
            return []
    
    def get_current_frequency(self, cpu=0):
        """获取当前频率"""
        try:
            freq_path = f'{self.cpu_base_path}/cpu{cpu}/cpufreq/scaling_cur_freq'
            with open(freq_path, 'r') as f:
                return int(f.read().strip())
        except Exception as e:
            logging.error(f"读取当前频率失败: {e}")
            return None
    
    def get_current_governor(self, cpu=0):
        """获取当前调频策略"""
        try:
            gov_path = f'{self.cpu_base_path}/cpu{cpu}/cpufreq/scaling_governor'
            with open(gov_path, 'r') as f:
                return f.read().strip()
        except Exception as e:
            logging.error(f"读取调频策略失败: {e}")
            return None
    
    def set_governor(self, governor='userspace', cpu=None):
        """设置调频策略为userspace模式"""
        cpus = [cpu] if cpu is not None else self.available_cpus
        
        for c in cpus:
            try:
                gov_path = f'{self.cpu_base_path}/cpu{c}/cpufreq/scaling_governor'
                cmd = f'echo {governor} | sudo tee {gov_path}'
                # Python 3.6兼容: 使用stdout和stderr代替capture_output
                subprocess.run(cmd, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                logging.info(f"CPU{c} 设置调频策略为 {governor}")
            except Exception as e:
                logging.error(f"设置CPU{c}调频策略失败: {e}")
                return False
        return True
    
    def set_frequency(self, frequency, cpu=None):
        """设置CPU频率
        
        Args:
            frequency: 目标频率(kHz)或频率索引
            cpu: CPU核心编号，None表示所有核心
        """
        cpus = [cpu] if cpu is not None else self.available_cpus
        
        # 确保在userspace模式
        current_gov = self.get_current_governor(cpus[0])
        if current_gov != 'userspace':
            logging.warning(f"当前调频策略为 {current_gov}，切换到 userspace")
            self.set_governor('userspace', cpu)
        
        # 如果frequency是0-1之间的小数，视为索引比例
        available_freqs = self.get_available_frequencies(cpus[0])
        if 0 < frequency < 1:
            idx = int(frequency * (len(available_freqs) - 1))
            target_freq = available_freqs[idx]
            logging.info(f"使用频率索引 {frequency:.2f} -> {target_freq} kHz")
        else:
            target_freq = int(frequency)
        
        # 验证频率是否可用
        if target_freq not in available_freqs:
            # 找到最接近的频率
            target_freq = min(available_freqs, key=lambda x: abs(x - target_freq))
            logging.warning(f"请求的频率不可用，使用最接近的频率: {target_freq} kHz")
        
        # 设置频率
        success_count = 0
        for c in cpus:
            try:
                freq_path = f'{self.cpu_base_path}/cpu{c}/cpufreq/scaling_setspeed'
                cmd = f'echo {target_freq} | sudo tee {freq_path}'
                # Python 3.6兼容: 使用stdout和stderr代替capture_output
                subprocess.run(cmd, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                logging.info(f"CPU{c} 频率设置为 {target_freq} kHz")
                success_count += 1
            except Exception as e:
                logging.error(f"设置CPU{c}频率失败: {e}")
        
        return success_count > 0
    
    def get_status(self):
        """获取所有CPU的当前状态"""
        status = {}
        for cpu in self.available_cpus:
            status[f'cpu{cpu}'] = {
                'current_freq': self.get_current_frequency(cpu),
                'governor': self.get_current_governor(cpu),
                'available_freqs': self.get_available_frequencies(cpu)
            }
        return status


class GPUController:
    """GPU频率控制器"""
    
    def __init__(self):
        # Jetson TX2 GPU路径
        self.gpu_paths = [
            '/sys/devices/gpu.0/devfreq/17000000.gp10b',
            '/sys/devices/17000000.gp10b/devfreq/17000000.gp10b',
            '/sys/kernel/debug/bpmp/debug/clk/gpcclk/rate',
            '/sys/devices/platform/gpu.0/devfreq/gpu.0'
        ]
        self.gpu_path = self.find_gpu_path()
        logging.info(f"初始化GPU控制器，GPU路径: {self.gpu_path}")
    
    def find_gpu_path(self):
        """查找GPU控制路径"""
        for path in self.gpu_paths:
            if os.path.exists(path):
                return path
        logging.warning("未找到GPU控制路径")
        return None
    
    def get_available_frequencies(self):
        """获取GPU可用频率列表"""
        if not self.gpu_path:
            return []
        
        try:
            freq_path = os.path.join(self.gpu_path, 'available_frequencies')
            if os.path.exists(freq_path):
                with open(freq_path, 'r') as f:
                    freqs = [int(x) for x in f.read().strip().split()]
                return sorted(freqs)
        except Exception as e:
            logging.error(f"读取GPU可用频率失败: {e}")
        
        # 如果无法读取，返回Jetson TX2常见的GPU频率
        return [76800000, 153600000, 230400000, 307200000, 384000000, 
                460800000, 537600000, 614400000, 691200000, 768000000, 
                844800000, 921600000, 998400000, 1075200000, 1152000000, 
                1228800000, 1267200000, 1300500000]
    
    def get_current_frequency(self):
        """获取当前GPU频率"""
        if not self.gpu_path:
            return None
        
        try:
            freq_path = os.path.join(self.gpu_path, 'cur_freq')
            if os.path.exists(freq_path):
                with open(freq_path, 'r') as f:
                    return int(f.read().strip())
        except Exception as e:
            logging.error(f"读取GPU当前频率失败: {e}")
        return None
    
    def get_current_governor(self):
        """获取当前调频策略"""
        if not self.gpu_path:
            return None
        
        try:
            gov_path = os.path.join(self.gpu_path, 'governor')
            if os.path.exists(gov_path):
                with open(gov_path, 'r') as f:
                    return f.read().strip()
        except Exception as e:
            logging.error(f"读取GPU调频策略失败: {e}")
        return None
    
    def set_governor(self, governor='userspace'):
        """设置GPU调频策略"""
        if not self.gpu_path:
            logging.error("GPU路径不存在")
            return False
        
        try:
            gov_path = os.path.join(self.gpu_path, 'governor')
            cmd = f'echo {governor} | sudo tee {gov_path}'
            subprocess.run(cmd, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            logging.info(f"GPU调频策略设置为 {governor}")
            return True
        except Exception as e:
            logging.error(f"设置GPU调频策略失败: {e}")
            return False
    
    def set_frequency(self, frequency):
        """设置GPU频率
        
        Args:
            frequency: 目标频率(Hz)或频率索引(0.0-1.0)
        """
        if not self.gpu_path:
            logging.error("GPU路径不存在")
            return False
        
        # 确保在userspace模式
        current_gov = self.get_current_governor()
        if current_gov != 'userspace':
            logging.warning(f"当前GPU调频策略为 {current_gov}，切换到 userspace")
            self.set_governor('userspace')
        
        # 如果frequency是0-1之间的小数，视为索引比例
        available_freqs = self.get_available_frequencies()
        if 0 < frequency < 1:
            idx = int(frequency * (len(available_freqs) - 1))
            target_freq = available_freqs[idx]
            logging.info(f"使用GPU频率索引 {frequency:.2f} -> {target_freq} Hz")
        else:
            target_freq = int(frequency)
        
        # 验证频率是否可用
        if target_freq not in available_freqs and available_freqs:
            # 找到最接近的频率
            target_freq = min(available_freqs, key=lambda x: abs(x - target_freq))
            logging.warning(f"请求的GPU频率不可用，使用最接近的频率: {target_freq} Hz")
        
        try:
            # 尝试多个可能的设置路径
            freq_paths = [
                os.path.join(self.gpu_path, 'userspace/freq'),
                os.path.join(self.gpu_path, 'min_freq'),
                os.path.join(self.gpu_path, 'max_freq')
            ]
            
            success = False
            for freq_path in freq_paths:
                if os.path.exists(freq_path):
                    try:
                        cmd = f'echo {target_freq} | sudo tee {freq_path}'
                        subprocess.run(cmd, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                        logging.info(f"GPU频率设置为 {target_freq} Hz ({target_freq/1000000:.1f} MHz)")
                        success = True
                    except Exception as e:
                        logging.debug(f"尝试设置 {freq_path} 失败: {e}")
            
            return success
        except Exception as e:
            logging.error(f"设置GPU频率失败: {e}")
            return False
    
    def get_status(self):
        """获取GPU当前状态"""
        return {
            'current_freq': self.get_current_frequency(),
            'governor': self.get_current_governor(),
            'available_freqs': self.get_available_frequencies(),
            'path': self.gpu_path
        }


def handle_client(conn, addr, cpu_controller, gpu_controller):
    """处理客户端连接"""
    print(f"{Colors.BRIGHT_GREEN}{'─' * 78}{Colors.RESET}")
    print(f"{Colors.BRIGHT_CYAN}✓ 客户端已连接: {Colors.BRIGHT_YELLOW}{addr[0]}:{addr[1]}{Colors.RESET}")
    logging.info(f"客户端已连接: {addr}")
    
    try:
        # 接收数据
        data = conn.recv(4096).decode('utf-8')
        if not data:
            return
        
        print(f"{Colors.DIM}收到命令: {data}{Colors.RESET}")
        logging.info(f"收到数据: {data}")
        
        # 解析JSON命令
        try:
            cmd = json.loads(data)
        except json.JSONDecodeError:
            response = {'status': 'error', 'message': '无效的JSON格式'}
            print(f"{Colors.RED}✗ 错误: 无效的JSON格式{Colors.RESET}")
            conn.sendall(json.dumps(response, ensure_ascii=False).encode('utf-8'))
            return
        
        # 处理命令
        action = cmd.get('action', '')
        target = cmd.get('target', 'cpu')  # 默认为CPU，可以是'cpu'或'gpu'
        response = {'status': 'success', 'timestamp': datetime.now().isoformat()}
        
        print(f"{Colors.CYAN}执行操作: {Colors.BOLD}{action}{Colors.RESET} {Colors.DIM}(目标: {target}){Colors.RESET}")
        
        # 选择控制器
        controller = cpu_controller if target == 'cpu' else gpu_controller
        
        if action == 'set_frequency':
            frequency = cmd.get('frequency')
            
            if frequency is None:
                response = {'status': 'error', 'message': '缺少frequency参数'}
                print(f"{Colors.RED}✗ 错误: 缺少frequency参数{Colors.RESET}")
            else:
                if target == 'cpu':
                    cpu = cmd.get('cpu', None)
                    success = controller.set_frequency(frequency, cpu)
                else:  # GPU
                    success = controller.set_frequency(frequency)
                
                if success:
                    response['message'] = f'{target.upper()}频率设置成功: {frequency}'
                    if target == 'cpu':
                        response['current_status'] = controller.get_status()
                    else:
                        response['gpu_status'] = controller.get_status()
                    print(f"{Colors.GREEN}✓ {target.upper()}频率设置成功{Colors.RESET}")
                else:
                    response = {'status': 'error', 'message': f'{target.upper()}频率设置失败'}
                    print(f"{Colors.RED}✗ {target.upper()}频率设置失败{Colors.RESET}")
        
        elif action == 'get_status':
            if target == 'all':
                response['cpu_status'] = cpu_controller.get_status()
                response['gpu_status'] = gpu_controller.get_status()
                response['message'] = 'CPU和GPU状态查询成功'
                print(f"{Colors.GREEN}✓ CPU和GPU状态查询成功{Colors.RESET}")
            elif target == 'cpu':
                response['status_info'] = controller.get_status()
                response['message'] = 'CPU状态查询成功'
                print(f"{Colors.GREEN}✓ CPU状态查询成功{Colors.RESET}")
            else:  # GPU
                response['gpu_status'] = controller.get_status()
                response['message'] = 'GPU状态查询成功'
                print(f"{Colors.GREEN}✓ GPU状态查询成功{Colors.RESET}")
        
        elif action == 'set_governor':
            governor = cmd.get('governor', 'userspace')
            
            if target == 'cpu':
                cpu = cmd.get('cpu', None)
                success = controller.set_governor(governor, cpu)
            else:  # GPU
                success = controller.set_governor(governor)
            
            if success:
                response['message'] = f'{target.upper()}调频策略设置成功: {governor}'
                print(f"{Colors.GREEN}✓ {target.upper()}调频策略设置为 {governor}{Colors.RESET}")
            else:
                response = {'status': 'error', 'message': f'{target.upper()}调频策略设置失败'}
                print(f"{Colors.RED}✗ {target.upper()}调频策略设置失败{Colors.RESET}")
        
        else:
            response = {'status': 'error', 'message': f'未知的操作: {action}'}
            print(f"{Colors.RED}✗ 未知的操作: {action}{Colors.RESET}")
        
        # 发送响应
        conn.sendall(json.dumps(response, ensure_ascii=False).encode('utf-8'))
        status = response['status']
        if status == 'success':
            print(f"{Colors.DIM}响应: {Colors.GREEN}{status}{Colors.RESET}")
        else:
            print(f"{Colors.DIM}响应: {Colors.RED}{status}{Colors.RESET}")
        logging.info(f"发送响应: {response['status']}")
        
    except Exception as e:
        logging.error(f"处理客户端请求时出错: {e}")
        print(f"{Colors.RED}✗ 处理请求时出错: {e}{Colors.RESET}")
        response = {'status': 'error', 'message': str(e)}
        try:
            conn.sendall(json.dumps(response, ensure_ascii=False).encode('utf-8'))
        except:
            pass
    
    finally:
        conn.close()
        print(f"{Colors.DIM}连接已关闭: {addr[0]}:{addr[1]}{Colors.RESET}")
        print(f"{Colors.BRIGHT_GREEN}{'─' * 78}{Colors.RESET}\n")
        logging.info(f"客户端连接关闭: {addr}")


def main():
    """主函数"""
    # 打印欢迎横幅
    print(f"\n{Colors.BOLD}{Colors.BRIGHT_CYAN}╔{'═' * 78}╗{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BRIGHT_CYAN}║{' ' * 28}边缘端DVFS服务{' ' * 33}║{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BRIGHT_CYAN}║{' ' * 20}Dynamic Voltage and Frequency Scaling{' ' * 20}║{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BRIGHT_CYAN}╚{'═' * 78}╝{Colors.RESET}\n")
    
    # 检查权限
    if os.geteuid() != 0:
        print(f"{Colors.YELLOW}⚠ 警告: 建议使用sudo运行以获得完整权限{Colors.RESET}\n")
    
    # 初始化控制器
    print(f"{Colors.DIM}正在初始化控制器...{Colors.RESET}")
    cpu_controller = CPUController()
    gpu_controller = GPUController()
    print(f"{Colors.GREEN}✓ 控制器初始化完成{Colors.RESET}\n")
    
    # 显示当前CPU状态
    print(f"{Colors.BOLD}{Colors.BRIGHT_GREEN}{'─' * 78}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BRIGHT_GREEN}当前CPU状态{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BRIGHT_GREEN}{'─' * 78}{Colors.RESET}")
    
    cpu_status = cpu_controller.get_status()
    for cpu_name, info in cpu_status.items():
        print(f"\n  {Colors.BRIGHT_CYAN}{cpu_name.upper()}:{Colors.RESET}")
        
        if info['current_freq']:
            freq_mhz = info['current_freq'] / 1000
            print(f"    当前频率: {Colors.BRIGHT_GREEN}{info['current_freq']} kHz ({freq_mhz:.1f} MHz){Colors.RESET}")
        else:
            print(f"    当前频率: {Colors.DIM}N/A{Colors.RESET}")
        
        # 调频策略用颜色区分
        gov = info['governor']
        if gov == 'userspace':
            gov_color = Colors.GREEN
        elif gov in ['performance', 'ondemand']:
            gov_color = Colors.YELLOW
        else:
            gov_color = Colors.RESET
        print(f"    调频策略: {gov_color}{gov}{Colors.RESET}")
        
        if info['available_freqs']:
            min_freq = min(info['available_freqs'])
            max_freq = max(info['available_freqs'])
            print(f"    可用频率: {Colors.DIM}{min_freq}-{max_freq} kHz ({len(info['available_freqs'])} 档){Colors.RESET}")
    
    # 显示当前GPU状态
    print(f"\n{Colors.BOLD}{Colors.BRIGHT_MAGENTA}{'─' * 78}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BRIGHT_MAGENTA}当前GPU状态{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BRIGHT_MAGENTA}{'─' * 78}{Colors.RESET}\n")
    
    gpu_status = gpu_controller.get_status()
    if gpu_status['current_freq']:
        freq_mhz = gpu_status['current_freq'] / 1000000
        print(f"  当前频率: {Colors.BRIGHT_GREEN}{gpu_status['current_freq']} Hz ({freq_mhz:.1f} MHz){Colors.RESET}")
    else:
        print(f"  当前频率: {Colors.DIM}N/A{Colors.RESET}")
    
    # 调频策略用颜色区分
    gov = gpu_status['governor']
    if gov == 'userspace':
        gov_color = Colors.GREEN
    elif gov in ['performance', 'simple_ondemand']:
        gov_color = Colors.YELLOW
    else:
        gov_color = Colors.RESET
    print(f"  调频策略: {gov_color}{gov}{Colors.RESET}")
    
    if gpu_status['available_freqs']:
        freqs_mhz = [f/1000000 for f in gpu_status['available_freqs']]
        print(f"  可用频率: {Colors.DIM}{min(freqs_mhz):.1f}-{max(freqs_mhz):.1f} MHz ({len(gpu_status['available_freqs'])} 档){Colors.RESET}")
    print(f"  控制路径: {Colors.DIM}{gpu_status['path']}{Colors.RESET}")
    
    # 启动TCP服务器
    print(f"\n{Colors.BOLD}{Colors.BRIGHT_YELLOW}{'─' * 78}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BRIGHT_YELLOW}启动TCP服务器{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BRIGHT_YELLOW}{'─' * 78}{Colors.RESET}")
    print(f"  监听地址: {Colors.BRIGHT_CYAN}{HOST}:{PORT}{Colors.RESET}")
    print(f"  日志文件: {Colors.DIM}{LOG_FILE}{Colors.RESET}")
    print(f"\n{Colors.BRIGHT_GREEN}✓ 服务器已启动，等待云端连接...{Colors.RESET}\n")
    
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        server_socket.bind((HOST, PORT))
        server_socket.listen(5)
        
        while True:
            conn, addr = server_socket.accept()
            handle_client(conn, addr, cpu_controller, gpu_controller)
    
    except KeyboardInterrupt:
        print(f"\n\n{Colors.BRIGHT_YELLOW}收到中断信号，正在关闭服务器...{Colors.RESET}")
        logging.info("服务器正常关闭")
    
    except Exception as e:
        logging.error(f"服务器错误: {e}")
        print(f"{Colors.RED}✗ 服务器错误: {e}{Colors.RESET}")
    
    finally:
        server_socket.close()
        print(f"{Colors.BRIGHT_GREEN}✓ 服务器已关闭{Colors.RESET}\n")


if __name__ == '__main__':
    main()

