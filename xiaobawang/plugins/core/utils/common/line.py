import matplotlib.pyplot as plt
import datetime
from typing import Dict, List, Any
import io
import base64


def generate_minimal_chart(history_data, width=800, height=200) -> str:
    """
    价格走势图

    Args:
        history_data: 包含物品历史数据的列表
        width: 图表宽度(像素)
        height: 图表高度(像素)

    Returns:
        str: data:image/png;base64,{img_str}
    """
    # 创建无边框图表
    fig = plt.figure(figsize=(width / 100, height / 100), dpi=100, frameon=False)
    ax = fig.add_subplot(111)

    # 使用最近三个月数据（90天）
    history = history_data[-90:] if len(history_data) > 90 else history_data

    if not history:
        return ''

    # 解析数据
    dates = [datetime.datetime.fromisoformat(entry['date']) for entry in history]
    avg_prices = [entry['average'] for entry in history]

    # 绘制亮蓝色折线（适合在黑色背景上更好地显示）
    ax.plot(dates, avg_prices, color='#4fc3f7', alpha=0.95, linewidth=2.5, solid_capstyle='round')

    # 填充下方区域，使用渐变色，更加明亮以适应黑色背景
    ax.fill_between(dates, avg_prices, min(avg_prices), color='#4fc3f7', alpha=0.2)

    # 完全移除所有边框和刻度
    for spine in ['top', 'right', 'left', 'bottom']:
        ax.spines[spine].set_visible(False)
    ax.set_xticks([])
    ax.set_yticks([])

    # 设置填充区域并确保没有多余的边距
    plt.subplots_adjust(left=0, right=1, top=1, bottom=0)

    # 转换为base64，确保图片是透明的
    buf = io.BytesIO()
    plt.savefig(buf, format='png', transparent=True, bbox_inches='tight', pad_inches=0)
    buf.seek(0)
    img_str = base64.b64encode(buf.read()).decode('ascii')
    plt.close(fig)

    return f'data:image/png;base64,{img_str}'