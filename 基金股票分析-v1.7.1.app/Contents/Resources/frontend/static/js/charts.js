// 图表渲染模块
const Charts = {
    chart: null,
    currentPeriod: 90,

    init() {
        const dom = document.getElementById('mainChart');
        if (!dom) return;
        this.chart = echarts.init(dom, 'dark');
        window.addEventListener('resize', () => this.chart?.resize());
    },

    async loadChart(code, category, period = 90) {
        this.currentPeriod = period;
        try {
            const data = await API.getHistory(code, category, period);
            if (!data.history || data.history.length === 0) {
                this.showEmpty('暂无历史数据');
                return;
            }
            this.renderCandlestick(data.history);
        } catch (e) {
            this.showEmpty('加载图表失败: ' + e.message);
        }
    },

    renderCandlestick(history) {
        if (!this.chart) return;

        const dates = history.map(d => d.date);
        const opens = history.map(d => d.open);
        const closes = history.map(d => d.close);
        const highs = history.map(d => d.high);
        const lows = history.map(d => d.low);
        const volumes = history.map(d => d.volume);

        // 计算均线
        const ma5 = this.calcMA(closes, 5);
        const ma10 = this.calcMA(closes, 10);
        const ma20 = this.calcMA(closes, 20);

        const option = {
            backgroundColor: 'transparent',
            grid: [
                { left: '8%', right: '8%', top: '5%', height: '60%' },
                { left: '8%', right: '8%', top: '72%', height: '20%' },
            ],
            xAxis: [
                {
                    type: 'category',
                    data: dates,
                    gridIndex: 0,
                    axisLine: { lineStyle: { color: '#2a2e3e' } },
                    axisLabel: { color: '#5c6072', fontSize: 11 },
                },
                {
                    type: 'category',
                    data: dates,
                    gridIndex: 1,
                    axisLine: { lineStyle: { color: '#2a2e3e' } },
                    axisLabel: { show: false },
                },
            ],
            yAxis: [
                {
                    gridIndex: 0,
                    scale: true,
                    axisLine: { lineStyle: { color: '#2a2e3e' } },
                    axisLabel: { color: '#5c6072', fontSize: 11 },
                    splitLine: { lineStyle: { color: '#1a1d27' } },
                },
                {
                    gridIndex: 1,
                    axisLine: { lineStyle: { color: '#2a2e3e' } },
                    axisLabel: { color: '#5c6072', fontSize: 10 },
                    splitLine: { show: false },
                },
            ],
            dataZoom: [
                { type: 'inside', xAxisIndex: [0, 1], start: 50, end: 100 },
            ],
            series: [
                {
                    name: 'K线',
                    type: 'candlestick',
                    xAxisIndex: 0,
                    yAxisIndex: 0,
                    data: history.map((d, i) => [opens[i], closes[i], lows[i], highs[i]]),
                    itemStyle: {
                        color: '#00b96b',
                        color0: '#f23b3b',
                        borderColor: '#00b96b',
                        borderColor0: '#f23b3b',
                    },
                },
                {
                    name: 'MA5',
                    type: 'line',
                    xAxisIndex: 0,
                    yAxisIndex: 0,
                    data: ma5,
                    smooth: true,
                    lineStyle: { width: 1, color: '#f59e0b' },
                    symbol: 'none',
                },
                {
                    name: 'MA10',
                    type: 'line',
                    xAxisIndex: 0,
                    yAxisIndex: 0,
                    data: ma10,
                    smooth: true,
                    lineStyle: { width: 1, color: '#3b82f6' },
                    symbol: 'none',
                },
                {
                    name: 'MA20',
                    type: 'line',
                    xAxisIndex: 0,
                    yAxisIndex: 0,
                    data: ma20,
                    smooth: true,
                    lineStyle: { width: 1, color: '#a855f7' },
                    symbol: 'none',
                },
                {
                    name: '成交量',
                    type: 'bar',
                    xAxisIndex: 1,
                    yAxisIndex: 1,
                    data: volumes,
                    itemStyle: {
                        color: (params) => {
                            const i = params.dataIndex;
                            return closes[i] >= opens[i] ? '#00b96b' : '#f23b3b';
                        },
                    },
                },
            ],
            tooltip: {
                trigger: 'axis',
                axisPointer: { type: 'cross' },
                backgroundColor: 'rgba(30, 33, 48, 0.95)',
                borderColor: '#2a2e3e',
                textStyle: { color: '#e4e6ed', fontSize: 12 },
            },
        };

        this.chart.setOption(option, true);
    },

    calcMA(data, period) {
        const result = [];
        for (let i = 0; i < data.length; i++) {
            if (i < period - 1) {
                result.push(null);
            } else {
                let sum = 0;
                for (let j = i - period + 1; j <= i; j++) {
                    sum += data[j];
                }
                result.push(+(sum / period).toFixed(2));
            }
        }
        return result;
    },

    showEmpty(msg) {
        if (this.chart) {
            this.chart.setOption({
                title: {
                    text: msg,
                    left: 'center',
                    top: 'center',
                    textStyle: { color: '#5c6072', fontSize: 14 },
                },
            }, true);
        }
    },
};