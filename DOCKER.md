# DVFS Docker 部署指南

本文档介绍如何使用 Docker 容器运行 DVFS 云边系统。

## 环境要求

- **云端服务器**: amd64 架构，已安装 Docker
- **边缘节点**: Jetson TX2 (arm64 架构)，已安装 Docker
- **私有镜像仓库**: 114.212.87.136:5000
- **基础镜像**: 使用私有仓库的Python镜像
  - `114.212.87.136:5000/python:3.9-slim-amd64` (云端)
  - `114.212.87.136:5000/python:3.9-slim-arm64` (边缘端)

## 快速开始

### 1. 构建镜像（在本地 amd64 虚拟机上）

**注意**: 确保私有仓库中的基础镜像已存在：
- `114.212.87.136:5000/python:3.9-slim-amd64`
- `114.212.87.136:5000/python:3.9-slim-arm64`

#### 方法一：使用简化构建脚本（推荐）

如果遇到buildx的HTTP私有仓库问题，使用简化构建脚本：

```bash
# 赋予构建脚本执行权限
chmod +x build-simple.sh

# 运行简化构建脚本
./build-simple.sh

# 选择选项 2: 构建并推送镜像
# 这会构建 amd64 和 arm64 两个版本的镜像并推送到私有仓库
```

#### 方法二：使用标准构建脚本

```bash
# 赋予构建脚本执行权限
chmod +x build.sh

# 运行构建脚本
./build.sh

# 选择选项 2: 构建并推送镜像
# 这会构建 amd64 和 arm64 两个版本的镜像并推送到私有仓库
# 云端镜像使用 amd64 基础镜像
# 边缘端镜像使用 arm64 基础镜像（Jetson TX2）
```

**可选：指定版本标签**
```bash
# 构建特定版本，例如 v1.0
./build.sh v1.0
```

### 2. 在边缘节点（Jetson TX2）上运行

#### 方式 A: 使用 docker-compose（推荐）

```bash
# 1. 拉取镜像
docker pull 114.212.87.136:5000/shy/dvfs-edge:latest

# 2. 使用 docker-compose 启动服务
docker-compose up -d dvfs-edge

# 3. 查看日志
docker-compose logs -f dvfs-edge

# 4. 停止服务
docker-compose down
```

#### 方式 B: 使用 docker run

```bash
# 拉取镜像
docker pull 114.212.87.136:5000/shy/dvfs-edge:latest

# 运行容器
docker run -d \
  --name dvfs-edge \
  --privileged \
  --network host \
  -v /sys/devices/system/cpu:/sys/devices/system/cpu \
  -v /sys/devices/gpu.0:/sys/devices/gpu.0:rw \
  -v /sys/devices/17000000.gp10b:/sys/devices/17000000.gp10b:rw \
  -v /sys/kernel/debug:/sys/kernel/debug:rw \
  -v /sys/devices/platform:/sys/devices/platform:rw \
  -v /tmp:/tmp \
  --restart unless-stopped \
  114.212.87.136:5000/shy/dvfs-edge:latest-arm64

# 查看日志
docker logs -f dvfs-edge

# 停止容器
docker stop dvfs-edge
docker rm dvfs-edge
```

### 3. 在云端使用客户端

#### 方式 A: 交互式容器

```bash
# 拉取镜像
docker pull 114.212.87.136:5000/shy/dvfs-cloud:latest

# 运行交互式容器
docker run -it --rm \
  --network host \
  -v ~/shy/id_rsa_shy:/root/.ssh/id_rsa_shy:ro \
  114.212.87.136:5000/shy/dvfs-cloud:latest \
  python3 cloud.py --use-tunnel --interactive

# 或者查看状态
docker run -it --rm \
  --network host \
  -v ~/shy/id_rsa_shy:/root/.ssh/id_rsa_shy:ro \
  114.212.87.136:5000/shy/dvfs-cloud:latest \
  python3 cloud.py --use-tunnel --status --target all
```

#### 方式 B: 快捷命令（创建别名）

在云端服务器的 `~/.bashrc` 或 `~/.zshrc` 中添加：

```bash
alias dvfs-cloud='docker run -it --rm --network host -v ~/shy/id_rsa_shy:/root/.ssh/id_rsa_shy:ro 114.212.87.136:5000/shy/dvfs-cloud:latest python3 cloud.py'
```

使用别名：
```bash
# 查看状态
dvfs-cloud --use-tunnel --status --target all

# 设置频率
dvfs-cloud --use-tunnel --freq 0.5

# 进入交互模式
dvfs-cloud --use-tunnel --interactive
```

## 常用命令

### 镜像管理

```bash
# 查看本地镜像
docker images | grep dvfs

# 删除镜像
docker rmi 114.212.87.136:5000/shy/dvfs-cloud:latest
docker rmi 114.212.87.136:5000/shy/dvfs-edge:latest

# 查看镜像详细信息
docker inspect 114.212.87.136:5000/shy/dvfs-edge:latest
```

### 容器管理

```bash
# 查看运行中的容器
docker ps | grep dvfs

# 查看所有容器（包括停止的）
docker ps -a | grep dvfs

# 进入容器
docker exec -it dvfs-edge /bin/bash

# 查看容器日志
docker logs dvfs-edge
docker logs -f dvfs-edge  # 持续查看

# 重启容器
docker restart dvfs-edge

# 停止并删除容器
docker stop dvfs-edge
docker rm dvfs-edge
```

## 注意事项

### 边缘端容器权限

边缘端容器需要 **特权模式** (`--privileged`) 才能访问系统的频率控制文件。这是因为：

1. CPU 频率控制需要访问 `/sys/devices/system/cpu/`
2. GPU 频率控制需要访问 `/sys/devices/gpu.0/` 等路径
3. 需要使用 `sudo` 命令写入系统文件

### SSH 密钥配置

如果使用 SSH 隧道模式，需要确保：
1. SSH 密钥文件在 `~/.ssh/` 目录下
2. SSH 配置正确（`~/.ssh/config`）
3. 密钥权限正确（`chmod 600 ~/.ssh/id_rsa`）

### 网络模式

- 边缘端使用 `--network host` 以监听 9999 端口
- 云端使用 `--network host` 以建立 SSH 隧道

### 私有镜像仓库

如果私有仓库需要认证：
```bash
# 登录私有仓库
docker login 114.212.87.136:5000

# 如果仓库使用 HTTP（非 HTTPS），需要配置 Docker daemon
# 编辑 /etc/docker/daemon.json
{
  "insecure-registries": ["114.212.87.136:5000"]
}

# 重启 Docker
sudo systemctl restart docker
```

## 故障排查

### 边缘端服务无法启动

1. 检查容器日志：
```bash
docker logs dvfs-edge
```

2. 检查挂载的系统目录是否存在：
```bash
ls -la /sys/devices/system/cpu/
ls -la /sys/devices/gpu.0/
```

3. 确认容器使用了特权模式

### 云端无法连接到边缘端

1. 检查 SSH 隧道是否建立成功
2. 检查边缘端容器是否在运行：`docker ps | grep dvfs-edge`
3. 检查网络连接：`telnet 114.212.81.186 15616`

### 镜像推送失败

1. 检查私有仓库是否可访问：
```bash
curl http://114.212.87.136:5000/v2/_catalog
```

2. 检查 Docker 配置中的 `insecure-registries`

### buildx HTTP私有仓库问题

如果遇到 `http: server gave HTTP response to HTTPS client` 错误：

1. **使用简化构建脚本**（推荐）：
```bash
./build-simple.sh
```

2. **安装多架构支持**（用于ARM64构建）：
```bash
docker run --privileged --rm tonistiigi/binfmt --install all
```

3. **检查buildx配置**：
```bash
docker buildx ls
docker buildx inspect multiarch-builder
```

4. **重新创建buildx builder**：
```bash
docker buildx rm multiarch-builder
docker buildx create --name multiarch-builder --use
```

### 多架构支持说明

项目使用 `tonistiigi/binfmt` 替代传统的 `qemu-user-static`：

**优势**：
- 更轻量级，性能更好
- 支持更多架构
- 自动处理binfmt配置
- 现代化的多架构支持方案

**安装**：
```bash
docker run --privileged --rm tonistiigi/binfmt --install all
```

**验证**：
```bash
# 检查binfmt配置
cat /proc/sys/fs/binfmt_misc/qemu-aarch64

# 测试运行ARM64容器
docker run --platform linux/arm64 ubuntu:20.04 uname -m
```

## 更新镜像

```bash
# 在本地构建机器上
./build.sh
# 选择 2: 构建并推送

# 在边缘节点上
docker pull 114.212.87.136:5000/shy/dvfs-edge:latest
docker-compose down
docker-compose up -d dvfs-edge

# 在云端（如果使用的是 latest 标签，自动使用新镜像）
docker pull 114.212.87.136:5000/shy/dvfs-cloud:latest
```

## 进阶使用

### 多版本管理

```bash
# 构建特定版本
./build.sh v1.0

# 使用特定版本
docker run ... 114.212.87.136:5000/shy/dvfs-edge:v1.0
```

### 自定义配置

如果需要修改默认配置（如端口、主机地址等），可以：

1. 修改 `edge.py` 或 `cloud.py` 中的配置
2. 重新构建镜像
3. 或者使用环境变量传递配置（需要修改代码支持环境变量）

## Dockerfile 说明

### 基础镜像配置

项目使用私有仓库的Python基础镜像：

- **云端镜像**: `114.212.87.136:5000/python:3.9-slim-amd64`
- **边缘端ARM64**: `114.212.87.136:5000/python:3.9-slim-arm64` (Jetson TX2)
- **边缘端AMD64**: `114.212.87.136:5000/python:3.9-slim-amd64` (云端测试)

### Dockerfile 文件

- `Dockerfile.cloud` - 云端客户端镜像
- `Dockerfile.edge` - 边缘端服务镜像（默认ARM64）
- `Dockerfile.edge.arm64` - 边缘端ARM64镜像（Jetson TX2）
- `Dockerfile.edge.amd64` - 边缘端AMD64镜像（云端测试）

### 多架构构建

构建脚本会自动：
1. 为ARM64架构构建边缘端镜像（使用arm64基础镜像）
2. 为AMD64架构构建边缘端镜像（使用amd64基础镜像）
3. 创建多架构manifest，支持自动架构选择

---

**完成！** 现在你的 DVFS 系统已经容器化并可以在云边环境中运行。

