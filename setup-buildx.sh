#!/bin/bash
# Docker Buildx 配置脚本 - 支持HTTP私有仓库

set -e

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo "======================================================================"
echo "               Docker Buildx 配置脚本"
echo "======================================================================"
echo ""

# 检查Docker是否运行
if ! docker info &> /dev/null; then
    echo -e "${RED}错误: Docker未运行${NC}"
    exit 1
fi

# 检查buildx是否可用
if ! docker buildx version &> /dev/null; then
    echo -e "${RED}错误: Docker buildx不可用${NC}"
    exit 1
fi

# 删除现有的builder（如果存在）
echo "清理现有的buildx builder..."
docker buildx rm multiarch-builder 2>/dev/null || true

# 创建新的builder
echo "创建支持HTTP私有仓库的buildx builder..."
docker buildx create \
    --name multiarch-builder \
    --driver docker-container \
    --driver-opt network=host \
    --use

# 启动builder
echo "启动buildx builder..."
docker buildx inspect --bootstrap

# 配置builder支持HTTP私有仓库
echo "配置builder支持HTTP私有仓库..."

# 方法1: 通过环境变量配置
export DOCKER_BUILDKIT=1
export BUILDX_NO_DEFAULT_ATTESTATIONS=1

# 方法2: 创建buildx配置文件
BUILDX_CONFIG_DIR="$HOME/.docker/buildx"
mkdir -p "$BUILDX_CONFIG_DIR"

# 创建buildx配置文件
cat > "$BUILDX_CONFIG_DIR/config.toml" << EOF
[worker.oci]
  insecure = true
  [[worker.oci.registry]]
    address = "114.212.87.136:5000"
    insecure = true
EOF

echo -e "${GREEN}✓ Buildx配置完成${NC}"
echo ""
echo "现在可以运行构建脚本了:"
echo "  ./build.sh"
echo ""
echo "如果仍然遇到问题，请尝试以下命令:"
echo "  docker buildx ls"
echo "  docker buildx inspect multiarch-builder"
