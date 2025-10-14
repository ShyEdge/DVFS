#!/bin/bash
# DVFS云边系统部署脚本
# 用于将文件部署到远程的cloud和edge5服务器

set -e  # 遇到错误立即退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 配置
CLOUD_HOST="cloud"
EDGE_HOST="edge5"
REMOTE_DIR="~/shy"
LOCAL_DIR="$(pwd)"

echo "======================================================================"
echo "                    DVFS云边系统部署脚本"
echo "======================================================================"
echo ""

# 检查SSH连接
check_ssh_connection() {
    local host=$1
    echo -n "检查与 ${host} 的SSH连接... "
    if ssh -o ConnectTimeout=5 -o BatchMode=yes ${host} exit &>/dev/null; then
        echo -e "${GREEN}OK${NC}"
        return 0
    else
        echo -e "${RED}失败${NC}"
        return 1
    fi
}

# 部署到云端
deploy_to_cloud() {
    echo ""
    echo ">>> 部署到云端 (${CLOUD_HOST})"
    echo "----------------------------------------------------------------------"
    
    # 检查连接
    if ! check_ssh_connection ${CLOUD_HOST}; then
        echo -e "${RED}无法连接到云端服务器${NC}"
        exit 1
    fi
    
    # 确保目录存在
    echo "确保远程目录存在..."
    ssh ${CLOUD_HOST} "mkdir -p ${REMOTE_DIR}"
    
    # 复制cloud.py
    echo "复制 cloud.py..."
    scp ${LOCAL_DIR}/cloud.py ${CLOUD_HOST}:${REMOTE_DIR}/
    
    # 设置权限
    echo "设置文件权限..."
    ssh ${CLOUD_HOST} "chmod +x ${REMOTE_DIR}/cloud.py"
    
    echo -e "${GREEN}云端部署完成！${NC}"
}

# 部署到边缘端
deploy_to_edge() {
    echo ""
    echo ">>> 部署到边缘端 (${EDGE_HOST})"
    echo "----------------------------------------------------------------------"
    
    # 检查连接
    if ! check_ssh_connection ${EDGE_HOST}; then
        echo -e "${RED}无法连接到边缘端服务器${NC}"
        exit 1
    fi
    
    # 确保目录存在
    echo "确保远程目录存在..."
    ssh ${EDGE_HOST} "mkdir -p ${REMOTE_DIR}"
    
    # 复制edge.py
    echo "复制 edge.py..."
    scp ${LOCAL_DIR}/edge.py ${EDGE_HOST}:${REMOTE_DIR}/
    
    # 设置权限
    echo "设置文件权限..."
    ssh ${EDGE_HOST} "chmod +x ${REMOTE_DIR}/edge.py"
    
    echo -e "${GREEN}边缘端部署完成！${NC}"
}

# 验证部署
verify_deployment() {
    echo ""
    echo ">>> 验证部署"
    echo "----------------------------------------------------------------------"
    
    echo "云端文件:"
    ssh ${CLOUD_HOST} "ls -lh ${REMOTE_DIR}/cloud.py" || echo -e "${RED}cloud.py 不存在${NC}"
    
    echo ""
    echo "边缘端文件:"
    ssh ${EDGE_HOST} "ls -lh ${REMOTE_DIR}/edge.py" || echo -e "${RED}edge.py 不存在${NC}"
}

# 显示使用说明
show_usage() {
    echo ""
    echo "======================================================================"
    echo "                          部署完成！"
    echo "======================================================================"
    echo ""
    echo "接下来的步骤："
    echo ""
    echo -e "${YELLOW}1. 在边缘端启动DVFS服务:${NC}"
    echo "   ssh edge5"
    echo "   cd ~/shy"
    echo "   sudo python3 edge.py"
    echo ""
    echo -e "${YELLOW}2. 在云端发送调频命令（使用SSH隧道）:${NC}"
    echo "   ssh cloud"
    echo "   cd ~/shy"
    echo ""
    echo "   # 查看边缘端状态（推荐使用SSH隧道）"
    echo "   python3 cloud.py --use-tunnel --status"
    echo ""
    echo "   # 设置频率到50%"
    echo "   python3 cloud.py --use-tunnel --freq 0.5"
    echo ""
    echo "   # 进入交互模式"
    echo "   python3 cloud.py --use-tunnel --interactive"
    echo ""
    echo "更多信息请查看 QUICKSTART.md"
    echo "======================================================================"
}

# 主流程
main() {
    # 检查必需的文件
    if [ ! -f "${LOCAL_DIR}/cloud.py" ]; then
        echo -e "${RED}错误: cloud.py 不存在${NC}"
        exit 1
    fi
    
    if [ ! -f "${LOCAL_DIR}/edge.py" ]; then
        echo -e "${RED}错误: edge.py 不存在${NC}"
        exit 1
    fi
    
    # 询问用户要部署到哪里
    echo "请选择部署目标:"
    echo "  1) 只部署到云端 (${CLOUD_HOST})"
    echo "  2) 只部署到边缘端 (${EDGE_HOST})"
    echo "  3) 部署到云端和边缘端"
    echo -n "请选择 [1-3]: "
    read choice
    
    case $choice in
        1)
            deploy_to_cloud
            ;;
        2)
            deploy_to_edge
            ;;
        3)
            deploy_to_cloud
            deploy_to_edge
            ;;
        *)
            echo -e "${RED}无效的选择${NC}"
            exit 1
            ;;
    esac
    
    verify_deployment
    show_usage
}

# 运行主流程
main

