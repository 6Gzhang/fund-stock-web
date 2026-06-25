// 主应用逻辑
const App = {
    currentStock: null, // { code, name, type, price }
    tradeAction: 'buy',
    searchDebounce: null,
    isComposing: false, // IME 输入法组合中

    init() {
        Charts.init();
        this.bindEvents();
        this.loadMarketIndex();
        this.loadTabContent('positions');
        this.loadTabContent('trades');
        this.loadTabContent('watchlist');
        this.checkVersion();
    },

    bindEvents() {
        // 搜索
        const searchInput = document.getElementById('searchInput');
        const searchBtn = document.getElementById('searchBtn');
        const searchResults = document.getElementById('searchResults');

        searchBtn.addEventListener('click', () => this.doSearch());

        searchInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !this.isComposing) {
                this.doSearch();
            }
        });

        // IME 输入法兼容：中文输入过程中不触发搜索
        searchInput.addEventListener('compositionstart', () => {
            this.isComposing = true;
        });
        searchInput.addEventListener('compositionend', (e) => {
            this.isComposing = false;
            // 输入法结束后，用最终文本触发搜索
            this.scheduleSearch();
        });

        // 普通输入：防抖 350ms
        searchInput.addEventListener('input', () => {
            if (!this.isComposing) {
                this.scheduleSearch();
            }
        });

        // 点击其他地方关闭搜索下拉
        document.addEventListener('click', (e) => {
            if (!searchResults.contains(e.target) && e.target !== searchInput && e.target !== searchBtn) {
                searchResults.style.display = 'none';
            }
        });

        // 标签页切换
        document.querySelectorAll('.tab').forEach(tab => {
            tab.addEventListener('click', () => {
                this.switchTab(tab.dataset.tab);
            });
        });

        // 图表周期
        document.querySelectorAll('.period-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.period-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                const period = parseInt(btn.dataset.period);
                if (this.currentStock) {
                    Charts.loadChart(this.currentStock.code, this.currentStock.type, period);
                }
            });
        });

        // 交易类型切换
        document.querySelectorAll('.trade-type-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.trade-type-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                this.tradeAction = btn.dataset.action;
            });
        });

        // 交易金额自动计算
        document.getElementById('tradePrice').addEventListener('input', () => this.updateTradeAmount());
        document.getElementById('tradeShares').addEventListener('input', () => this.updateTradeAmount());

        // 提交交易
        document.getElementById('tradeSubmit').addEventListener('click', () => this.executeTrade());
    },

    // ========== 搜索（防抖 + 加载状态 + 请求取消） ==========
    scheduleSearch() {
        if (this.searchDebounce) clearTimeout(this.searchDebounce);
        const keyword = document.getElementById('searchInput').value.trim();
        if (keyword.length < 1) {
            document.getElementById('searchResults').style.display = 'none';
            return;
        }
        this.searchDebounce = setTimeout(() => this.doSearch(), 350);
    },

    async doSearch() {
        const keyword = document.getElementById('searchInput').value.trim();
        const category = document.getElementById('searchCategory').value;
        const searchResults = document.getElementById('searchResults');

        if (!keyword) {
            searchResults.style.display = 'none';
            return;
        }

        // 显示加载状态
        searchResults.innerHTML = '<div class="search-result-item"><span style="color:#8b8fa3">搜索中...</span></div>';
        searchResults.style.display = 'block';

        try {
            const data = await API.search(keyword, category);
            this.renderSearchResults(data.results);
        } catch (e) {
            // 忽略被取消的请求
            if (e.name === 'AbortError') return;
            searchResults.innerHTML = `<div class="search-result-item"><span style="color:#f23b3b">搜索失败: ${e.message}</span></div>`;
            searchResults.style.display = 'block';
        }
    },

    renderSearchResults(results) {
        const searchResults = document.getElementById('searchResults');
        if (!results || results.length === 0) {
            searchResults.innerHTML = '<div class="search-result-item"><span style="color:#5c6072">未找到结果</span></div>';
            searchResults.style.display = 'block';
            return;
        }

        const typeLabels = { stock: '股票', fund: '基金', etf: 'ETF' };
        searchResults.innerHTML = results.map(r => `
            <div class="search-result-item" data-code="${r.code}" data-name="${r.name}" data-type="${r.type}">
                <div class="info">
                    <span class="name">${r.name}</span>
                    <span class="code">${r.code} · ${typeLabels[r.type] || r.type}</span>
                </div>
                <div class="price-info">
                    <div class="price">${r.price.toFixed(r.type === 'fund' ? 4 : 2)}</div>
                    <div style="font-size:13px;color:${r.change_pct >= 0 ? 'var(--green)' : 'var(--red)'}">
                        ${r.change_pct >= 0 ? '+' : ''}${r.change_pct.toFixed(2)}%
                    </div>
                </div>
            </div>
        `).join('');

        searchResults.style.display = 'block';

        // 绑定点击
        searchResults.querySelectorAll('.search-result-item').forEach(item => {
            item.addEventListener('click', () => {
                this.selectStock(item.dataset.code, item.dataset.name, item.dataset.type);
                searchResults.style.display = 'none';
                document.getElementById('searchInput').value = '';
            });
        });
    },

    // ========== 选择标的 ==========
    async selectStock(code, name, type) {
        this.currentStock = { code, name, type };
        document.getElementById('tradeCard').style.display = 'block';

        // 加载行情
        await this.loadQuote(code, type);
        // 加载图表
        Charts.loadChart(code, type, Charts.currentPeriod);
        // 加载 AI 分析
        this.loadAnalysis(code, type);
        // 切换回行情页
        this.switchTab('market');
    },

    async loadQuote(code, type) {
        try {
            const quote = await API.getQuote(code, type);
            this.currentStock.price = quote.price;
            this.renderQuote(quote);
            document.getElementById('tradePrice').value = quote.price;
            this.updateTradeAmount();
        } catch (e) {
            console.error('加载行情失败:', e);
        }
    },

    renderQuote(quote) {
        const card = document.getElementById('quoteCard');
        const changeColor = quote.change_pct >= 0 ? 'var(--green)' : 'var(--red)';
        const changeSign = quote.change_pct >= 0 ? '+' : '';

        card.innerHTML = `
            <div class="stock-name">${quote.name}</div>
            <div class="stock-code">${quote.code}</div>
            <div class="stock-price" style="color:${changeColor}">${quote.price.toFixed(quote.type === 'fund' ? 4 : 2)}</div>
            <div class="stock-change" style="color:${changeColor}">
                ${changeSign}${quote.change.toFixed(quote.type === 'fund' ? 4 : 2)}  ${changeSign}${quote.change_pct.toFixed(2)}%
            </div>
            <div class="stock-detail">
                <div class="detail-item"><span class="detail-label">今开</span><span>${quote.open.toFixed(2)}</span></div>
                <div class="detail-item"><span class="detail-label">最高</span><span style="color:var(--green)">${quote.high.toFixed(2)}</span></div>
                <div class="detail-item"><span class="detail-label">最低</span><span style="color:var(--red)">${quote.low.toFixed(2)}</span></div>
                <div class="detail-item"><span class="detail-label">成交量</span><span>${this.formatVolume(quote.volume)}</span></div>
            </div>
        `;
    },

    // ========== AI 分析 ==========
    async loadAnalysis(code, type) {
        const card = document.getElementById('aiCard');
        card.innerHTML = '<h3>AI 智能分析</h3><div class="card-placeholder">分析中...</div>';

        try {
            const result = await API.analyzeStock(code, type);
            const recLabels = { buy: '买入', sell: '卖出', hold: '持有' };
            const rec = result.recommendation;

            card.innerHTML = `
                <h3>AI 智能分析</h3>
                <div class="ai-status">
                    <span class="dot ${result.ai_available ? 'online' : ''}"></span>
                    ${result.ai_available ? 'AI 模型在线' : '简易分析模式（配置 API Key 启用 AI）'}
                </div>
                <div class="recommendation-badge ${rec}">${recLabels[rec] || rec}</div>
                <div class="confidence">置信度: ${(result.confidence * 100).toFixed(0)}%</div>
                <div class="reasoning">${result.reasoning}</div>
                <div class="suggested-ratio">
                    建议仓位占比: <span>${(result.suggested_ratio * 100).toFixed(1)}%</span>
                </div>
            `;
        } catch (e) {
            card.innerHTML = `<h3>AI 智能分析</h3><div class="card-placeholder">分析失败: ${e.message}</div>`;
        }
    },

    // ========== 交易 ==========
    updateTradeAmount() {
        const price = parseFloat(document.getElementById('tradePrice').value) || 0;
        const shares = parseFloat(document.getElementById('tradeShares').value) || 0;
        document.getElementById('tradeAmount').value = (price * shares).toFixed(2);
    },

    async executeTrade() {
        if (!this.currentStock) {
            alert('请先选择一只股票或基金');
            return;
        }

        const price = parseFloat(document.getElementById('tradePrice').value);
        const shares = parseFloat(document.getElementById('tradeShares').value);

        if (!price || !shares || shares <= 0) {
            alert('请输入有效的价格和数量');
            return;
        }

        try {
            await API.executeTrade({
                code: this.currentStock.code,
                name: this.currentStock.name,
                type: this.currentStock.type,
                action: this.tradeAction,
                shares: shares,
                price: price,
            });
            alert(`${this.tradeAction === 'buy' ? '买入' : '卖出'}成功！`);
            document.getElementById('tradeShares').value = '';
            this.updateTradeAmount();
            this.loadTabContent('positions');
            this.loadTabContent('trades');
        } catch (e) {
            alert('交易失败: ' + e.message);
        }
    },

    // ========== 标签页 ==========
    switchTab(tabName) {
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

        const targetTab = document.querySelector(`.tab[data-tab="${tabName}"]`);
        const targetContent = document.getElementById(`tab-${tabName}`);
        if (targetTab) targetTab.classList.add('active');
        if (targetContent) targetContent.classList.add('active');

        this.loadTabContent(tabName);

        if (tabName === 'market' && Charts.chart) {
            Charts.chart.resize();
        }
    },

    async loadTabContent(tabName) {
        switch (tabName) {
            case 'positions': await this.loadPositions(); break;
            case 'trades': await this.loadTrades(); break;
            case 'watchlist': await this.loadWatchlist(); break;
        }
    },

    // ========== 持仓 ==========
    async loadPositions() {
        try {
            const data = await API.getPositions();
            const positions = data.positions;

            const totalValue = positions.reduce((s, p) => s + p.market_value, 0);
            const totalCost = positions.reduce((s, p) => s + p.avg_cost * p.shares, 0);
            const totalProfit = totalValue - totalCost;
            const totalProfitPct = totalCost > 0 ? (totalProfit / totalCost * 100) : 0;

            document.getElementById('positionsSummary').innerHTML = `
                <div class="summary-item">
                    <span class="sum-label">总市值</span>
                    <span class="sum-value">${totalValue.toFixed(2)}</span>
                </div>
                <div class="summary-item">
                    <span class="sum-label">总成本</span>
                    <span class="sum-value">${totalCost.toFixed(2)}</span>
                </div>
                <div class="summary-item">
                    <span class="sum-label">总盈亏</span>
                    <span class="sum-value" style="color:${totalProfit >= 0 ? 'var(--green)' : 'var(--red)'}">
                        ${totalProfit >= 0 ? '+' : ''}${totalProfit.toFixed(2)}
                    </span>
                </div>
                <div class="summary-item">
                    <span class="sum-label">收益率</span>
                    <span class="sum-value" style="color:${totalProfitPct >= 0 ? 'var(--green)' : 'var(--red)'}">
                        ${totalProfitPct >= 0 ? '+' : ''}${totalProfitPct.toFixed(2)}%
                    </span>
                </div>
            `;

            const tbody = document.querySelector('#positionsTable tbody');
            const typeLabels = { stock: '股票', fund: '基金', etf: 'ETF' };
            tbody.innerHTML = positions.map(p => `
                <tr>
                    <td>${p.code}</td>
                    <td>${p.name}</td>
                    <td>${typeLabels[p.type] || p.type}</td>
                    <td>${p.shares}</td>
                    <td>${p.avg_cost.toFixed(4)}</td>
                    <td>${p.current_price.toFixed(4)}</td>
                    <td>${p.market_value.toFixed(2)}</td>
                    <td class="${p.profit >= 0 ? 'profit-positive' : 'profit-negative'}">${p.profit >= 0 ? '+' : ''}${p.profit.toFixed(2)}</td>
                    <td class="${p.profit_pct >= 0 ? 'profit-positive' : 'profit-negative'}">${p.profit_pct >= 0 ? '+' : ''}${p.profit_pct.toFixed(2)}%</td>
                </tr>
            `).join('') || '<tr><td colspan="9" style="text-align:center;color:var(--text-muted);padding:30px">暂无持仓</td></tr>';
        } catch (e) {
            console.error('加载持仓失败:', e);
        }
    },

    // ========== 交易记录 ==========
    async loadTrades() {
        try {
            const data = await API.getTrades();
            const trades = data.trades;
            const typeLabels = { stock: '股票', fund: '基金', etf: 'ETF' };

            const tbody = document.querySelector('#tradesTable tbody');
            tbody.innerHTML = trades.map(t => `
                <tr>
                    <td>${new Date(t.created_at).toLocaleString('zh-CN')}</td>
                    <td>${t.code}</td>
                    <td>${t.name}</td>
                    <td>${typeLabels[t.type] || t.type}</td>
                    <td style="color:${t.action === 'buy' ? 'var(--green)' : 'var(--red)'}">${t.action === 'buy' ? '买入' : '卖出'}</td>
                    <td>${t.shares}</td>
                    <td>${t.price.toFixed(4)}</td>
                    <td>${t.amount.toFixed(2)}</td>
                </tr>
            `).join('') || '<tr><td colspan="8" style="text-align:center;color:var(--text-muted);padding:30px">暂无交易记录</td></tr>';
        } catch (e) {
            console.error('加载交易记录失败:', e);
        }
    },

    // ========== 自选 ==========
    async loadWatchlist() {
        try {
            const data = await API.getWatchlist();
            const watchlist = data.watchlist;
            const typeLabels = { stock: '股票', fund: '基金', etf: 'ETF' };

            const tbody = document.querySelector('#watchlistTable tbody');
            tbody.innerHTML = watchlist.map(w => `
                <tr>
                    <td>${w.code}</td>
                    <td>${w.name}</td>
                    <td>${typeLabels[w.type] || w.type}</td>
                    <td>
                        <button class="btn btn-sm btn-primary" onclick="App.selectStock('${w.code}','${w.name}','${w.type}')">查看</button>
                        <button class="btn btn-sm btn-danger" onclick="App.removeWatchlist('${w.code}')">删除</button>
                    </td>
                </tr>
            `).join('') || '<tr><td colspan="4" style="text-align:center;color:var(--text-muted);padding:30px">暂无自选</td></tr>';
        } catch (e) {
            console.error('加载自选失败:', e);
        }
    },

    async removeWatchlist(code) {
        try {
            await API.removeFromWatchlist(code);
            this.loadWatchlist();
        } catch (e) {
            alert('删除失败: ' + e.message);
        }
    },

    // ========== 大盘指数 ==========
    async loadMarketIndex() {
        try {
            const indices = await API.getMarketIndex();
            const container = document.getElementById('marketIndices');
            if (Object.keys(indices).length === 0) {
                container.innerHTML = '<span class="index-loading">暂无指数数据</span>';
                return;
            }
            container.innerHTML = Object.entries(indices).map(([name, data]) => `
                <div class="index-item">
                    <span class="name">${name}</span>
                    <span class="price">${data.price.toFixed(2)}</span>
                    <span style="color:${data.change_pct >= 0 ? 'var(--green)' : 'var(--red)'};font-size:12px">
                        ${data.change_pct >= 0 ? '+' : ''}${data.change_pct.toFixed(2)}%
                    </span>
                </div>
            `).join('');
        } catch (e) {
            console.error('加载指数失败:', e);
        }
    },

    // ========== 工具函数 ==========
    formatVolume(vol) {
        if (vol >= 1e8) return (vol / 1e8).toFixed(2) + '亿';
        if (vol >= 1e4) return (vol / 1e4).toFixed(2) + '万';
        return vol.toString();
    },

    // ========== 版本检查 ==========
    async checkVersion() {
        try {
            const data = await API.getVersion();
            document.getElementById('versionText').textContent = 'v' + data.version;

            // 检查更新按钮事件
            document.getElementById('versionCheckBtn').addEventListener('click', async () => {
                await this.doVersionCheck(data.version);
            });
        } catch (e) {
            console.error('获取版本失败:', e);
        }
    },

    async doVersionCheck(currentVersion) {
        const btn = document.getElementById('versionCheckBtn');
        btn.style.animation = 'spin 1s linear infinite';

        try {
            const response = await fetch('https://api.github.com/repos/6Gzhang/fund-stock-web/releases/latest');
            if (!response.ok) throw new Error('检查更新失败');

            const data = await response.json();
            const latestVersion = data.tag_name ? data.tag_name.replace(/^v/, '') : currentVersion;

            if (latestVersion > currentVersion) {
                const updateMsg = `发现新版本 v${latestVersion}！\n\n更新内容：\n${data.body || '暂无更新说明'}\n\n是否前往下载？`;
                if (confirm(updateMsg)) {
                    window.open(data.html_url, '_blank');
                }
            } else {
                alert('当前已是最新版本 (v' + currentVersion + ')');
            }
        } catch (e) {
            alert('检查更新失败: ' + e.message);
        } finally {
            btn.style.animation = '';
        }
    },
};

// 启动应用
document.addEventListener('DOMContentLoaded', () => App.init());