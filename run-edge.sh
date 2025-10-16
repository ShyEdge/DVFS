#!/bin/bash
# 边缘端DVFS服务快速启动脚本

set -e

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 配置
REG="114.212.87.136:5000"
IMAGE="${REG}/shy/dvfs-edge:latest"
CONTAINER_NAME="dvfs-edge"

echo "======================================================================"
echo "              边缘端DVFS服务启动脚本"
echo "======================================================================"
echo ""

# 检查是否已有容器在运行
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo -e "${YELLOW}检测到已存在的容器: ${CONTAINER_NAME}${NC}"
    echo -n "是否要删除并重新启动? [y/N]: "
    read answer
    if [[ "$answer" =~ ^[Yy]$ ]]; then
        echo "停止并删除旧容器..."
        docker stop ${CONTAINER_NAME} 2>/dev/null || true
        docker rm ${CONTAINER_NAME} 2>/dev/null || true
    else
        echo "取消操作"
        exit 0
    fi
fi

# 拉取最新镜像
echo "拉取最新镜像..."
docker pull ${IMAGE}

# 启动容器
echo ""
echo "启动边缘端服务..."
docker run -d \
  --name ${CONTAINER_NAME} \
  --privileged \
  --network host \
  -v /sys/devices/system/cpu:/sys/devices/system/cpu \
  -v /sys/devices/gpu.0:/sys/devices/gpu.0:rw \
  -v /sys/devices/17000000.gp10b:/sys/devices/17000000.gp10b:rw \
  -v /sys/kernel/debug:/sys/kernel/debug:rw \
  -v /sys/devices/platform:/sys/devices/platform:rw \
  -v /tmp:/tmp \
  --restart unless-stopped \
  ${IMAGE}

echo ""
echo -e "${GREEN}✓ 边缘端服务已启动！${NC}"
echo ""
echo "常用命令:"
echo "  查看日志:    docker logs -f ${CONTAINER_NAME}"
echo "  停止服务:    docker stop ${CONTAINER_NAME}"
echo "  重启服务:    docker restart ${CONTAINER_NAME}"
echo "  进入容器:    docker exec -it ${CONTAINER_NAME} /bin/bash"
echo ""
echo "正在显示实时日志（按 Ctrl+C 退出）..."
echo "======================================================================"
sleep 2
docker logs -f ${CONTAINER_NAME}

