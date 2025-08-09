import base64
import datetime
import io

import matplotlib.pyplot as plt


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
    fig = plt.figure(figsize=(width / 100, height / 100), dpi=100, frameon=False)
    ax = fig.add_subplot(111)

    history = history_data[-90:] if len(history_data) > 90 else history_data

    if not history:
        return ""

    try:
        dates = []
        avg_prices = []
        for entry in history:
            if isinstance(entry, dict) and "date" in entry and "average" in entry:
                dates.append(datetime.datetime.fromisoformat(entry["date"]))
                avg_prices.append(float(entry["average"]))
            elif isinstance(entry, str):
                try:
                    entry_dict = eval(entry)
                    if "date" in entry_dict and "average" in entry_dict:
                        dates.append(datetime.datetime.fromisoformat(entry_dict["date"]))
                        avg_prices.append(float(entry_dict["average"]))
                except Exception:
                    continue

        if not dates or not avg_prices:
            return ""

        trend_up = avg_prices[-1] > avg_prices[0]

        line_color = "#4CAF50" if trend_up else "#F44336"
        fill_color = line_color

        ax.plot(dates, avg_prices, color=line_color, alpha=0.95, linewidth=2.5, solid_capstyle="round")

        ax.fill_between(dates, avg_prices, min(avg_prices), color=fill_color, alpha=0.2)

        for spine in ["top", "right", "left", "bottom"]:
            ax.spines[spine].set_visible(False)
        ax.set_xticks([])
        ax.set_yticks([])

        plt.subplots_adjust(left=0, right=1, top=1, bottom=0)

        buf = io.BytesIO()
        plt.savefig(buf, format="png", transparent=True, bbox_inches="tight", pad_inches=0)
        buf.seek(0)
        img_str = base64.b64encode(buf.read()).decode("ascii")
        plt.close(fig)

        return f"data:image/png;base64,{img_str}"
    except Exception:
        plt.close(fig)
        return ""
