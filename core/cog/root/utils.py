import io
from datetime import datetime, timedelta

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import MaxNLocator


def generate_timeline_graph(timeline_data: dict, title: str = "Activity Timeline", timeframe_days: int | None = None) -> io.BytesIO:
	fig, ax = plt.subplots(figsize=(7, 3))

	if not timeline_data:
		timeline_data = {datetime.now().strftime("%Y-%m-%d %H:00"): 0}

	parsed_data = {datetime.strptime(d, "%Y-%m-%d %H:%M"): v for d, v in timeline_data.items()}

	if timeframe_days is not None:
		cutoff_date = datetime.now() - timedelta(days=timeframe_days)
		parsed_data = {d: v for d, v in parsed_data.items() if d >= cutoff_date}

	if not parsed_data:
		parsed_data = {datetime.now().replace(minute=0, second=0, microsecond=0): 0}

	max_date = max(parsed_data.keys())
	min_date = min(parsed_data.keys())

	if (max_date - min_date).total_seconds() < 24 * 3600:
		min_date = max_date - timedelta(hours=23)

	dates = []
	values = []
	current_date = min_date

	while current_date <= max_date:
		dates.append(current_date)
		values.append(parsed_data.get(current_date, 0))
		current_date += timedelta(hours=1)

	ax.plot(dates, values, marker='o', color='#00E9FE', linestyle='-', linewidth=2, markersize=4)
	ax.fill_between(dates, values, color='#00E9FE', alpha=0.1)

	time_span = max_date - min_date
	if time_span.total_seconds() <= 48 * 3600:
		ax.xaxis.set_major_formatter(mdates.DateFormatter('%I %p'))
	else:
		ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))

	ax.yaxis.set_major_locator(MaxNLocator(integer=True))
	ax.set_ylim(bottom=0)

	ax.spines['top'].set_visible(False)
	ax.spines['right'].set_visible(False)
	ax.spines['left'].set_color('#B0B8C1')
	ax.spines['bottom'].set_color('#B0B8C1')
	ax.tick_params(colors='#B0B8C1')
	ax.grid(color='gray', linestyle='--', linewidth=0.5, alpha=0.3)

	plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha='right', color='#B0B8C1')
	plt.setp(ax.yaxis.get_majorticklabels(), color='#B0B8C1')

	plt.title(title, color='#B0B8C1', pad=10)
	plt.tight_layout()

	buf = io.BytesIO()
	plt.savefig(buf, format='png', transparent=True)
	buf.seek(0)
	plt.close(fig)

	return buf
