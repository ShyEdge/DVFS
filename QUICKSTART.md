# DVFS云边系统快速启动指南

## 系统概述

本系统实现了云边协同的动态电压频率调整（DVFS），云端可以远程控制边缘端（Jetson TX2）的CPU频率。

### 系统架构

```
本地电脑
   │
   ├─── SSH ──> 云端 (cloud)
   │              └─── cloud.py (发送调频命令)
   │                     │
   │                     │ SSH隧道 (端口15616, 使用id_rsa_shy)
   │                     └──────────────────┐
   │                                         │
   └─── SSH ──> 边缘端 (114.212.81.186)    │
                  └─── edge.py (接收并执行) <─┘
                       监听端口 9999
```

**连接方式**:
- **SSH隧道模式（推荐，已配置）**: cloud.py通过SSH隧道连接到 nvidia@114.212.81.186:9999
  - SSH用户名: nvidia
  - SSH端口: 15616
  - 使用密钥: ~/shy/id_rsa_shy
- **直接连接模式**: 仅在云端能直接访问边缘端IP时使用

### 文件说明

- **cloud.py**: 云端控制脚本，用于向边缘端发送调频命令
- **edge.py**: 边缘端服务脚本，监听并执行调频命令
- **deploy.sh**: 自动部署脚本，将文件复制到远程服务器
- **QUICKSTART.md**: 本文档

---

## 快速开始

### 步骤1: 部署文件

在本地电脑上运行部署脚本：

```bash
cd /Users/shy/Desktop/DVFS
chmod +x deploy.sh
./deploy.sh
```

根据提示选择：
- 选项 3: 同时部署到云端和边缘端

部署脚本会自动将文件复制到远程服务器的 `~/shy` 目录。

---

### 步骤2: 启动边缘端服务

在**边缘端 (edge5)** 上启动DVFS服务：

```bash
# 从本地连接到边缘端
ssh edge5

# 进入工作目录
cd ~/shy

# 启动边缘端服务（需要sudo权限）
sudo python3 edge.py
```

**输出示例：**
```
============================================================
边缘端DVFS服务启动
============================================================

当前CPU状态:
  cpu0:
    当前频率: 2035200 kHz
    调频策略: schedutil
    可用频率: 345600-2035200 kHz
  ...

启动TCP服务器 0.0.0.0:9999
日志文件: /tmp/dvfs_edge.log
等待云端连接...
```

服务启动后会监听 9999 端口，等待云端的连接。

---

### 步骤3: 从云端发送调频命令

打开**另一个终端**，连接到**云端 (cloud)**：

```bash
# 从本地连接到云端
ssh cloud

# 进入工作目录
cd ~/shy
```

**重要提示**: 由于云端和边缘端之间可能存在网络隔离，推荐使用 `--use-tunnel` 参数通过SSH隧道连接。

#### 3.1 查询边缘端状态

**使用SSH隧道（推荐）：**

```bash
python3 cloud.py --use-tunnel --status
```

**直接连接（如果网络互通）：**

```bash
python3 cloud.py --status
```

**输出示例：**
```
============================================================
边缘端CPU状态
============================================================

CPU0:
  当前频率: 2035200 kHz (2035.2 MHz)
  调频策略: userspace
  可用频率: 8 档
    最低: 345600 kHz (345.6 MHz)
    最高: 2035200 kHz (2035.2 MHz)
...
============================================================
```

#### 3.2 设置CPU频率

使用**频率索引**（推荐方式）：

```bash
# 设置到最低频率（0.0 = 最低档）
python3 cloud.py --use-tunnel --freq 0.0

# 设置到中等频率（0.5 = 中间档）
python3 cloud.py --use-tunnel --freq 0.5

# 设置到最高频率（1.0 = 最高档）
python3 cloud.py --use-tunnel --freq 1.0

# 设置到80%频率
python3 cloud.py --use-tunnel --freq 0.8
```

使用**具体频率值**（单位：kHz）：

```bash
# 设置到1.2GHz
python3 cloud.py --use-tunnel --freq 1200000

# 设置到最低频率345.6MHz
python3 cloud.py --use-tunnel --freq 345600
```

指定**特定CPU核心**：

```bash
# 只设置CPU0到50%频率
python3 cloud.py --use-tunnel --freq 0.5 --cpu 0

# 只设置CPU1到最高频率
python3 cloud.py --use-tunnel --freq 1.0 --cpu 1
```

#### 3.3 设置调频策略

```bash
# 设置为userspace模式（用于手动控制频率）
python3 cloud.py --use-tunnel --governor userspace

# 设置为performance模式（最高性能）
python3 cloud.py --use-tunnel --governor performance

# 设置为powersave模式（最低功耗）
python3 cloud.py --use-tunnel --governor powersave
```

#### 3.4 交互模式

进入交互模式进行连续操作：

```bash
python3 cloud.py --use-tunnel --interactive
```

在交互模式中，可以使用简化的命令：

```
DVFS> help                # 显示帮助
DVFS> status              # 查询状态
DVFS> freq 0.5            # 设置频率到50%
DVFS> freq 1200000        # 设置频率到1.2GHz
DVFS> freq 0.8 0          # 设置CPU0到80%频率
DVFS> governor userspace  # 设置调频策略
DVFS> quit                # 退出
```

---

## SSH隧道说明

### 为什么使用SSH隧道？

在云边架构中，云端服务器和边缘端设备之间可能存在网络隔离，导致云端无法直接访问边缘端的IP地址和端口。SSH隧道通过SSH连接建立一个加密的端口转发通道，解决这个问题。

### SSH隧道工作原理

```
云端 (cloud)                          边缘端 (nvidia@114.212.81.186:15616)
    |                                      |
    |  1. SSH连接 (使用id_rsa_shy)        |
    |     ssh -p 15616 -i ~/shy/id_rsa_shy nvidia@114.212.81.186
    |------------------------------------>|
    |                                      |
    |  2. 建立端口转发                     |
    |     localhost:19999 -> edge5:9999   |
    |                                      |
    |  3. 发送DVFS命令到localhost:19999   |
    |------------------------------------>|
    |     (自动转发到114.212.81.186:9999) |
```

### 使用方法

只需在所有命令中添加 `--use-tunnel` 参数：

```bash
# 基本用法（使用默认配置）
python3 cloud.py --use-tunnel --status

# 自定义SSH用户名（默认使用 nvidia）
python3 cloud.py --use-tunnel --ssh-user nvidia --status

# 自定义SSH密钥（默认使用 ~/shy/id_rsa_shy）
python3 cloud.py --use-tunnel --ssh-key ~/.ssh/custom_key --status

# 自定义SSH端口（默认使用 15616）
python3 cloud.py --use-tunnel --ssh-port 15616 --status

# 自定义本地端口（默认使用 19999）
python3 cloud.py --use-tunnel --local-port 20000 --status
```

### 默认配置

- **边缘端IP**: 114.212.81.186
- **SSH用户名**: nvidia
- **SSH端口**: 15616
- **DVFS服务端口**: 9999
- **SSH密钥**: ~/shy/id_rsa_shy
- **本地隧道端口**: 19999

### SSH隧道自动管理

程序会自动：
- 建立SSH隧道连接
- 验证隧道是否成功建立
- 在程序退出时自动清理隧道
- 处理连接失败的情况

---

## 详细使用说明

### 频率控制说明

Jetson TX2支持多个频率档位，通过 `cloud.py` 可以灵活控制：

1. **频率索引方式**（0.0 - 1.0）
   - 0.0 表示最低频率
   - 1.0 表示最高频率
   - 中间值按比例对应可用频率档位
   - 推荐使用此方式，更加直观

2. **绝对频率方式**（单位：kHz）
   - 直接指定目标频率值
   - 如果指定的频率不在可用列表中，系统会自动选择最接近的可用频率

### 调频策略说明

- **userspace**: 用户空间控制，可通过程序设置频率（DVFS必须）
- **performance**: 始终使用最高频率
- **powersave**: 始终使用最低频率
- **schedutil**: 根据CPU负载动态调整（默认策略）
- **ondemand**: 根据负载快速切换频率

**注意**: 进行DVFS控制前，必须先设置为 `userspace` 模式。

### 指定CPU核心

Jetson TX2有多个CPU核心：
- Denver CPU: cpu0, cpu1
- ARM A57 CPU: cpu2, cpu3, cpu4, cpu5

可以通过 `--cpu` 参数指定要控制的核心，或者不指定以控制所有核心。

---

## 常见问题

### Q1: 连接被拒绝 (Connection Refused) 或无法解析主机名

**原因**: 边缘端服务未启动、网络不通或主机名无法解析。

**解决方案（推荐）**: 使用SSH隧道

```bash
# 在cloud上使用SSH隧道连接
python3 cloud.py --use-tunnel --status
```

**其他解决方案**:
```bash
# 在edge5上检查服务是否运行
ssh edge5
ps aux | grep edge.py

# 如果没有运行，启动服务
cd ~/shy
sudo python3 edge.py
```

### Q2: 权限被拒绝 (Permission Denied)

**原因**: 调整CPU频率需要root权限。

**解决**:
```bash
# 在edge5上使用sudo运行
sudo python3 edge.py
```

### Q3: 频率设置失败

**原因**: 调频策略不是 userspace。

**解决**:
```bash
# 先设置调频策略为userspace
python3 cloud.py --governor userspace

# 然后再设置频率
python3 cloud.py --freq 0.5
```

### Q4: SSH隧道建立失败

**原因**: SSH密钥权限问题或网络连接失败。

**解决**:
```bash
# 在cloud上检查SSH密钥权限
ls -l ~/shy/id_rsa_shy
# 应该显示 -rw------- (权限600)

# 如果权限不对，修改权限
chmod 600 ~/shy/id_rsa_shy

# 测试SSH连接（使用正确的用户名、端口和IP）
ssh -i ~/shy/id_rsa_shy -p 15616 nvidia@114.212.81.186 hostname

# 或者如果配置了edge5别名
ssh -i ~/shy/id_rsa_shy nvidia@edge5 hostname
```

### Q5: 查看日志

边缘端的运行日志保存在 `/tmp/dvfs_edge.log`：

```bash
ssh edge5
tail -f /tmp/dvfs_edge.log
```

---

## 高级用法

### 1. 自定义主机和端口

```bash
# 指定不同的边缘端主机
python3 cloud.py --host 192.168.1.100 --port 9999 --status

# 设置超时时间
python3 cloud.py --timeout 30 --status
```

### 2. 编写自动化脚本

创建一个频率调整策略脚本：

```bash
#!/bin/bash
# 示例：模拟动态调频

echo "开始动态调频测试"

# 低频运行10秒
echo "设置低频..."
ssh cloud "cd ~/shy && python3 cloud.py --freq 0.0"
sleep 10

# 中频运行10秒
echo "设置中频..."
ssh cloud "cd ~/shy && python3 cloud.py --freq 0.5"
sleep 10

# 高频运行10秒
echo "设置高频..."
ssh cloud "cd ~/shy && python3 cloud.py --freq 1.0"
sleep 10

echo "测试完成"
```

### 3. Python脚本调用

在云端可以直接在Python代码中导入使用：

```python
from cloud import CloudDVFSClient

# 创建客户端
client = CloudDVFSClient(host='edge5', port=9999)

# 获取状态
response = client.get_status()
print(response)

# 设置频率
response = client.set_frequency(0.5)
print(response)
```

---

## 系统要求

### 云端 (cloud)
- Python 3.10.9
- 网络能够访问edge5

### 边缘端 (edge5 - Jetson TX2)
- Python 3.6.9+
- Linux系统（支持cpufreq子系统）
- sudo权限（用于调整CPU频率）
- 开放TCP端口9999

---

## 安全注意事项

1. **端口安全**: 默认使用9999端口，确保该端口只在内部网络开放
2. **权限控制**: edge.py需要root权限，请确保系统安全
3. **SSH密钥**: 使用SSH密钥认证，避免密码泄露

---

## 故障排查清单

- [ ] 边缘端服务是否正在运行？(`ps aux | grep edge.py`)
- [ ] 云端能否ping通边缘端？(`ping edge5`)
- [ ] 端口9999是否开放？(`netstat -tuln | grep 9999`)
- [ ] 是否有sudo权限？
- [ ] Python版本是否正确？(`python3 --version`)
- [ ] 查看日志文件：`/tmp/dvfs_edge.log`

---

## 联系与支持

如遇问题，请检查：
1. 边缘端日志：`/tmp/dvfs_edge.log`
2. 确认网络连通性
3. 验证SSH配置

---

**祝使用愉快！**

