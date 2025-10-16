#!/bin/bash
# Docker镜像构建和推送脚本

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 配置
REG="114.212.87.136:5000"
REPO="shy"
VERSION="${1:-latest}"

echo "======================================================================"
echo "                    DVFS Docker镜像构建脚本"
echo "======================================================================"
echo ""
echo "镜像仓库: ${REG}"
echo "命名空间: ${REPO}"
echo "版本标签: ${VERSION}"
echo ""

# 检查Docker是否安装
if ! command -v docker &> /dev/null; then
    echo -e "${RED}错误: Docker未安装${NC}"
    exit 1
fi

# 检查buildx是否可用
if ! docker buildx version &> /dev/null; then
    echo -e "${YELLOW}警告: docker buildx不可用，将使用普通构建${NC}"
    USE_BUILDX=false
else
    USE_BUILDX=true
fi

# 构建云端镜像 (amd64)
build_cloud() {
    echo ""
    echo -e "${BLUE}>>> 构建云端镜像 (amd64)${NC}"
    echo "----------------------------------------------------------------------"
    
    IMAGE_NAME="${REG}/${REPO}/dvfs-cloud:${VERSION}"
    
    if [ "$USE_BUILDX" = true ]; then
        docker buildx build \
            --platform linux/amd64 \
            --file Dockerfile.cloud \
            --build-arg BASE_IMAGE=114.212.87.136:5000/python:3.9-slim-amd64 \
            --tag ${IMAGE_NAME} \
            --tag ${REG}/${REPO}/dvfs-cloud:latest \
            --load \
            .
    else
        docker build \
            --file Dockerfile.cloud \
            --build-arg BASE_IMAGE=114.212.87.136:5000/python:3.9-slim-amd64 \
            --tag ${IMAGE_NAME} \
            --tag ${REG}/${REPO}/dvfs-cloud:latest \
            .
    fi
    
    echo -e "${GREEN}✓ 云端镜像构建完成: ${IMAGE_NAME}${NC}"
}

# 构建边缘端镜像 (arm64 和 amd64)
build_edge() {
    echo ""
    echo -e "${BLUE}>>> 构建边缘端镜像 (arm64, amd64)${NC}"
    echo "----------------------------------------------------------------------"
    
    IMAGE_NAME="${REG}/${REPO}/dvfs-edge:${VERSION}"
    
    if [ "$USE_BUILDX" = true ]; then
        # 创建或使用buildx builder
        if ! docker buildx inspect multiarch-builder &> /dev/null; then
            echo "创建多架构构建器..."
            # 创建支持HTTP私有仓库的buildx builder
            docker buildx create \
                --name multiarch-builder \
                --driver docker-container \
                --driver-opt network=host \
                --use
        else
            docker buildx use multiarch-builder
        fi
        
        # 配置buildx builder支持HTTP私有仓库
        echo "配置buildx builder支持HTTP私有仓库..."
        docker buildx inspect --bootstrap
        
        # 设置环境变量支持HTTP私有仓库
        export DOCKER_BUILDKIT=1
        export BUILDX_NO_DEFAULT_ATTESTATIONS=1
        
        # 安装多架构支持
        echo "安装tonistiigi/binfmt多架构支持..."
        docker run --privileged --rm tonistiigi/binfmt --install all
        
        echo "注意: 多架构镜像将在推送时构建"
        echo "现在先构建当前架构的镜像用于本地测试..."
        docker buildx build \
            --platform linux/amd64 \
            --file Dockerfile.edge.amd64 \
            --tag ${IMAGE_NAME} \
            --tag ${REG}/${REPO}/dvfs-edge:latest \
            --load \
            .
    else
        echo -e "${YELLOW}警告: 没有buildx，只构建当前架构${NC}"
        docker build \
            --file Dockerfile.edge.amd64 \
            --tag ${IMAGE_NAME} \
            --tag ${REG}/${REPO}/dvfs-edge:latest \
            .
    fi
    
    echo -e "${GREEN}✓ 边缘端镜像构建完成: ${IMAGE_NAME}${NC}"
}

# 推送镜像
push_images() {
    echo ""
    echo -e "${BLUE}>>> 推送镜像到私有仓库${NC}"
    echo "----------------------------------------------------------------------"
    
    # 推送云端镜像
    echo "推送云端镜像..."
    docker push ${REG}/${REPO}/dvfs-cloud:${VERSION}
    docker push ${REG}/${REPO}/dvfs-cloud:latest
    
    # 推送边缘端镜像
    echo "推送边缘端镜像..."
    if [ "$USE_BUILDX" = true ]; then
        # 使用buildx推送多架构镜像
        echo "构建并推送多架构边缘端镜像..."
        echo "  - ARM64版本 (Jetson TX2)"
        echo "  - AMD64版本 (云端测试)"
        
        # 构建并推送多架构镜像
        docker buildx build \
            --platform linux/arm64,linux/amd64 \
            --file Dockerfile.edge.arm64 \
            --tag ${REG}/${REPO}/dvfs-edge:${VERSION}-arm64 \
            --tag ${REG}/${REPO}/dvfs-edge:latest-arm64 \
            --push \
            .
            
        docker buildx build \
            --platform linux/amd64 \
            --file Dockerfile.edge.amd64 \
            --tag ${REG}/${REPO}/dvfs-edge:${VERSION}-amd64 \
            --tag ${REG}/${REPO}/dvfs-edge:latest-amd64 \
            --push \
            .
        
        # 创建多架构manifest
        echo "创建多架构manifest..."
        docker manifest create ${REG}/${REPO}/dvfs-edge:${VERSION} \
            ${REG}/${REPO}/dvfs-edge:${VERSION}-arm64 \
            ${REG}/${REPO}/dvfs-edge:${VERSION}-amd64
            
        docker manifest create ${REG}/${REPO}/dvfs-edge:latest \
            ${REG}/${REPO}/dvfs-edge:latest-arm64 \
            ${REG}/${REPO}/dvfs-edge:latest-amd64
        
        # 推送manifest
        docker manifest push ${REG}/${REPO}/dvfs-edge:${VERSION}
        docker manifest push ${REG}/${REPO}/dvfs-edge:latest
    else
        docker push ${REG}/${REPO}/dvfs-edge:${VERSION}
        docker push ${REG}/${REPO}/dvfs-edge:latest
    fi
    
    echo -e "${GREEN}✓ 所有镜像推送完成${NC}"
}

# 显示镜像信息
show_images() {
    echo ""
    echo -e "${BLUE}>>> 本地镜像列表${NC}"
    echo "----------------------------------------------------------------------"
    docker images | grep "dvfs-" || echo "没有找到DVFS镜像"
}

# 主流程
main() {
    echo "请选择操作:"
    echo "  1) 只构建镜像"
    echo "  2) 构建并推送镜像"
    echo "  3) 只推送镜像"
    echo "  4) 查看本地镜像"
    echo -n "请选择 [1-4]: "
    read choice
    
    case $choice in
        1)
            build_cloud
            build_edge
            show_images
            ;;
        2)
            build_cloud
            build_edge
            push_images
            show_images
            ;;
        3)
            push_images
            ;;
        4)
            show_images
            ;;
        *)
            echo -e "${RED}无效的选择${NC}"
            exit 1
            ;;
    esac
    
    echo ""
    echo "======================================================================"
    echo -e "${GREEN}操作完成！${NC}"
    echo "======================================================================"
}

# 运行主流程
main

