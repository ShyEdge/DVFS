#!/bin/bash
# 简化的Docker镜像构建脚本 - 避免buildx的HTTP私有仓库问题

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
echo "               DVFS Docker镜像简化构建脚本"
echo "======================================================================"
echo ""
echo "镜像仓库: ${REG}"
echo "命名空间: ${REPO}"
echo "版本标签: ${VERSION}"
echo ""

# 构建云端镜像 (amd64)
build_cloud() {
    echo ""
    echo -e "${BLUE}>>> 构建云端镜像 (amd64)${NC}"
    echo "----------------------------------------------------------------------"
    
    IMAGE_NAME="${REG}/${REPO}/dvfs-cloud:${VERSION}"
    
    docker build \
        --file Dockerfile.cloud \
        --tag ${IMAGE_NAME} \
        --tag ${REG}/${REPO}/dvfs-cloud:latest \
        .
    
    echo -e "${GREEN}✓ 云端镜像构建完成: ${IMAGE_NAME}${NC}"
}

# 构建边缘端镜像 (amd64)
build_edge_amd64() {
    echo ""
    echo -e "${BLUE}>>> 构建边缘端镜像 (amd64)${NC}"
    echo "----------------------------------------------------------------------"
    
    IMAGE_NAME="${REG}/${REPO}/dvfs-edge:${VERSION}-amd64"
    
    docker build \
        --file Dockerfile.edge.amd64 \
        --tag ${IMAGE_NAME} \
        --tag ${REG}/${REPO}/dvfs-edge:latest-amd64 \
        .
    
    echo -e "${GREEN}✓ 边缘端AMD64镜像构建完成: ${IMAGE_NAME}${NC}"
}

# 设置多架构支持
setup_binfmt() {
    echo ""
    echo -e "${BLUE}>>> 设置多架构支持${NC}"
    echo "----------------------------------------------------------------------"
    
    echo "安装tonistiigi/binfmt多架构支持..."
    if docker run --privileged --rm tonistiigi/binfmt --install all; then
        echo -e "${GREEN}✓ 多架构支持安装成功${NC}"
    else
        echo -e "${RED}✗ 多架构支持安装失败${NC}"
        return 1
    fi
}

# 构建边缘端镜像 (arm64) - 使用tonistiigi/binfmt
build_edge_arm64() {
    echo ""
    echo -e "${BLUE}>>> 构建边缘端镜像 (arm64)${NC}"
    echo "----------------------------------------------------------------------"
    
    IMAGE_NAME="${REG}/${REPO}/dvfs-edge:${VERSION}-arm64"
    
    docker build \
        --file Dockerfile.edge.arm64 \
        --tag ${IMAGE_NAME} \
        --tag ${REG}/${REPO}/dvfs-edge:latest-arm64 \
        .
    
    echo -e "${GREEN}✓ 边缘端ARM64镜像构建完成: ${IMAGE_NAME}${NC}"
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
    docker push ${REG}/${REPO}/dvfs-edge:${VERSION}-amd64
    docker push ${REG}/${REPO}/dvfs-edge:latest-amd64
    
    # 推送ARM64镜像（如果存在）
    if docker images | grep -q "${REG}/${REPO}/dvfs-edge.*arm64"; then
        docker push ${REG}/${REPO}/dvfs-edge:${VERSION}-arm64
        docker push ${REG}/${REPO}/dvfs-edge:latest-arm64
    fi
    
    echo -e "${GREEN}✓ 所有镜像推送完成${NC}"
}

# 创建多架构manifest
create_manifest() {
    echo ""
    echo -e "${BLUE}>>> 创建多架构manifest${NC}"
    echo "----------------------------------------------------------------------"
    
    # 检查是否安装了manifest工具
    if ! docker manifest --help &> /dev/null; then
        echo -e "${YELLOW}警告: Docker manifest工具不可用${NC}"
        echo "请升级Docker到支持manifest的版本"
        return 1
    fi
    
    # 创建manifest
    echo "创建多架构manifest..."
    docker manifest create ${REG}/${REPO}/dvfs-edge:${VERSION} \
        ${REG}/${REPO}/dvfs-edge:${VERSION}-amd64 \
        ${REG}/${REPO}/dvfs-edge:${VERSION}-arm64 2>/dev/null || \
    docker manifest create ${REG}/${REPO}/dvfs-edge:${VERSION} \
        ${REG}/${REPO}/dvfs-edge:${VERSION}-amd64
    
    docker manifest create ${REG}/${REPO}/dvfs-edge:latest \
        ${REG}/${REPO}/dvfs-edge:latest-amd64 \
        ${REG}/${REPO}/dvfs-edge:latest-arm64 2>/dev/null || \
    docker manifest create ${REG}/${REPO}/dvfs-edge:latest \
        ${REG}/${REPO}/dvfs-edge:latest-amd64
    
    # 推送manifest
    docker manifest push ${REG}/${REPO}/dvfs-edge:${VERSION}
    docker manifest push ${REG}/${REPO}/dvfs-edge:latest
    
    echo -e "${GREEN}✓ 多架构manifest创建完成${NC}"
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
    echo "  5) 安装多架构支持"
    echo -n "请选择 [1-5]: "
    read choice
    
    case $choice in
        1)
            build_cloud
            build_edge_amd64
            setup_binfmt
            build_edge_arm64
            show_images
            ;;
        2)
            build_cloud
            build_edge_amd64
            setup_binfmt
            build_edge_arm64
            push_images
            create_manifest
            show_images
            ;;
        3)
            push_images
            create_manifest
            ;;
        4)
            show_images
            ;;
        5)
            echo "安装多架构支持..."
            setup_binfmt
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
