"""图表层测试：文件名必须用交易日。"""

from datetime import date

import pandas as pd
import pytest

from src import chart


def test_render_chart_names_file_by_trading_day(history_frame):
    path = chart.render_chart(history_frame, today=date(2026, 9, 14))
    assert path.name == "2026-09-14.png"
    assert path.exists()
    assert path.stat().st_size > 1000


def test_render_chart_needs_at_least_two_points(history_frame):
    with pytest.raises(ValueError):
        chart.render_chart(history_frame.tail(1))


def test_render_chart_on_empty_data():
    with pytest.raises(ValueError):
        chart.render_chart(pd.DataFrame())
