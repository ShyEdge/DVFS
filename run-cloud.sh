#!/bin/bash
# 云端DVFS客户端快速使用脚本

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 配置
REG="114.212.87.136:5000"
IMAGE="${REG}/shy/dvfs-cloud:latest"

# 检查SSH密钥文件
if [ ! -f "$HOME/shy/id_rsa_shy" ]; then
    echo -e "${YELLOW}警告: SSH密钥文件不存在: $HOME/shy/id_rsa_shy${NC}"
    SSH_MOUNT=""
else
    SSH_MOUNT="-v $HOME/shy/id_rsa_shy:/root/.ssh/id_rsa_shy:ro"
fi

# 显示帮助
show_help() {
    echo "======================================================================"
    echo "              云端DVFS客户端使用脚本"
    echo "======================================================================"
    echo ""
    echo "用法: $0 [选项]"
    echo ""
    echo "选项:"
    echo "  status        查询边缘端CPU状态"
    echo "  status-gpu    查询边缘端GPU状态"
    echo "  status-all    查询边缘端所有状态"
    echo "  interactive   进入交互模式"
    echo "  pull          拉取最新镜像"
    echo "  help          显示此帮助信息"
    echo ""
    echo "示例:"
    echo "  $0 status          # 查询CPU状态"
    echo "  $0 interactive     # 进入交互模式"
    echo "  $0 pull            # 拉取最新镜像"
    echo ""
    echo "自定义命令:"
    echo "  docker run -it --rm --network host $SSH_MOUNT \\"
    echo "    $IMAGE \\"
    echo "    python3 cloud.py --use-tunnel [你的参数]"
    echo "======================================================================"
}

# 拉取镜像
pull_image() {
    echo "拉取最新镜像..."
    docker pull ${IMAGE}
    echo -e "${GREEN}✓ 镜像拉取完成${NC}"
}

# 执行命令
run_command() {
    local cmd="$1"
    echo -e "${BLUE}>>> 执行命令: ${cmd}${NC}"
    echo ""
    docker run -it --rm \
        --network host \
        ${SSH_MOUNT} \
        ${IMAGE} \
        python3 cloud.py --use-tunnel ${cmd}
}

# 主程序
case "$1" in
    status)
        run_command "--status --target cpu"
        ;;
    status-gpu)
        run_command "--status --target gpu"
        ;;
    status-all)
        run_command "--status --target all"
        ;;
    interactive|i)
        run_command "--interactive"
        ;;
    pull)
        pull_image
        ;;
    help|--help|-h|"")
        show_help
        ;;
    *)
        echo -e "${YELLOW}未知选项: $1${NC}"
        echo ""
        show_help
        exit 1
        ;;
esac

