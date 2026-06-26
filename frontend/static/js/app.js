// 主应用逻辑
const App = {
    currentStock: null,
    tradeAction: 'buy',
    searchDebounce: null,
    isComposing: false,
    recommendType: 'all',
    recommendRiskTier: 'all',
    recommendPollTimer: null,
    chatMessages: [],
    isChatLoading: false,

    init() {
        Charts.init();
        this.bindEvents();
        this.loadMarketIndex();
        this.loadTabContent('positions');
        this.loadTabContent('trades');
        this.loadTabContent('watchlist');
        this.checkVersion();
        this.pollDataStatus();
        this.loadRecommendations();
    },

    bindEvents() {
        const searchInput = document.getElementById('searchInput');
        const searchBtn = document.getElementById('searchBtn');
        const searchResults = document.getElementById('searchResults');

        searchBtn.addEventListener('click', () => this.doSearch());

        searchInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !this.isComposing) {
                this.doSearch();
            }
        });

        searchInput.addEventListener('compositionstart', () => {
            this.isComposing = true;
        });
        searchInput.addEventListener('compositionend', (e) => {
            this.isComposing = false;
            this.scheduleSearch();
        });

        searchInput.addEventListener('input', () => {
            if (!this.isComposing) {
                this.scheduleSearch();
            }
        });

        document.addEventListener('click', (e) => {
            if (!searchResults.contains(e.target) && e.target !== searchInput && e.target !== searchBtn) {
                searchResults.style.display = 'none';
            }
        });

        document.querySelectorAll('.tab').forEach(tab => {
            tab.addEventListener('click', () => {
                this.switchTab(tab.dataset.tab);
            });
        });

        document.querySelectorAll('.recommend-tab').forEach(tab => {
            tab.addEventListener('click', () => {
                document.querySelectorAll('.recommend-tab').forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                this.recommendType = tab.dataset.type;
                this.renderRecommendations();
            });
        });

        document.querySelectorAll('.recommend-risk-tab').forEach(tab => {
            tab.addEventListener('click', () => {
                document.querySelectorAll('.recommend-risk-tab').forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                this.recommendRiskTier = tab.dataset.tier;
                this.renderRecommendations();
            });
        });

        const refreshBtn = document.getElementById('refreshRecommendBtn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => {
                this.refreshRecommendations();
            });
        }

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

        document.querySelectorAll('.trade-type-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                document.querySelectorAll('.trade-type-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                this.tradeAction = btn.dataset.action;
                this.updateTradeAmount();
            });
        });

        const tradeShares = document.getElementById('tradeShares');
        const tradePrice = document.getElementById('tradePrice');
        if (tradeShares) tradeShares.addEventListener('input', () => this.updateTradeAmount());
        if (tradePrice) tradePrice.addEventListener('input', () => this.updateTradeAmount());

        const tradeSubmit = document.getElementById('tradeSubmit');
        if (tradeSubmit) tradeSubmit.addEventListener('click', () => this.doTrade());

        const versionCheckBtn = document.getElementById('versionCheckBtn');
        if (versionCheckBtn) versionCheckBtn.addEventListener('click', () => this.checkVersion(true));

        const versionText = document.getElementById('versionText');
        if (versionText) versionText.addEventListener('click', () => this.checkVersion(true));

        const chatSendBtn = document.getElementById('chatSendBtn');
        const chatInput = document.getElementById('chatInput');
        const chatClearBtn = document.getElementById('chatClearBtn');

        if (chatSendBtn) {
            chatSendBtn.addEventListener('click', () => this.sendChatMessage());
        }

        if (chatInput) {
            chatInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    this.sendChatMessage();
                }
            });
        }

        if (chatClearBtn) {
            chatClearBtn.addEventListener('click', () => this.clearChatHistory());
        }
    },

    switchTab(tabName) {
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
        document.querySelector(`.tab[data-tab="${tabName}"]`).classList.add('active');
        document.getElementById(`tab-${tabName}`).classList.add('active');

        if (tabName === 'recommend') {
            this.loadRecommendations();
        }
        if (tabName === 'market') {
            setTimeout(() => Charts.resize(), 100);
        }
        if (tabName === 'chat') {
            this.updateChatContext();
        }
    },

    scheduleSearch() {
        clearTimeout(this.searchDebounce);
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

        searchResults.innerHTML = '<div class="search-loading">搜索中...</div>';
        searchResults.style.display = 'block';

        try {
            const results = await API.search(keyword, category);
            if (results.length === 0) {
                searchResults.innerHTML = '<div class="search-loading">暂无匹配结果</div>';
                return;
            }
            this.renderSearchResults(results);
        } catch (e) {
            searchResults.innerHTML = `<div class="search-error">搜索失败：${e.message}</div>`;
        }
    },

    renderSearchResults(results) {
        const searchResults = document.getElementById('searchResults');
        const typeLabels = {
            stock: '股票', etf: 'ETF', fund: '基金', stock_hk: '港股', index: '指数'
        };

        searchResults.innerHTML = results.map(item => `
            <div class="search-result-item" data-code="${item.code}" data-name="${item.name}" data-type="${item.type}">
                <div class="search-result-info">
                    <span class="search-result-name">
                        ${item.name}
                        <span class="search-result-type type-${item.type}">${typeLabels[item.type] || item.type}</span>
                    </span>
                    <span class="search-result-code">${item.code}</span>
                </div>
                <div class="search-result-price">
                    <div class="price ${item.change_pct >= 0 ? 'up' : 'down'}">${item.price.toFixed(2)}</div>
                    <div class="change ${item.change_pct >= 0 ? 'up' : 'down'}">${item.change_pct >= 0 ? '+' : ''}${item.change_pct.toFixed(2)}%</div>
                </div>
            </div>
        `).join('');

        searchResults.querySelectorAll('.search-result-item').forEach(el => {
            el.addEventListener('click', () => {
                const code = el.dataset.code;
                const name = el.dataset.name;
                const type = el.dataset.type;
                this.selectQuote(code, name, type);
                searchResults.style.display = 'none';
            });
        });
    },

    selectQuote(code, name, type) {
        this.currentStock = { code, name, type };
        this.switchTab('market');

        setTimeout(async () => {
            this.loadQuote(code, type);
            Charts.loadChart(code, type, 30);
            this.loadAnalysis(code, type);
            this.updateChatContext();
        }, 100);
    },

    async loadQuote(code, type) {
        const quoteCard = document.getElementById('quoteCard');
        const tradeCard = document.getElementById('tradeCard');

        try {
            const quote = type === 'fund' ? await API.getFundQuote(code) : await API.getStockQuote(code);
            if (!quote) {
                quoteCard.innerHTML = '<div class="card-placeholder">暂无行情数据</div>';
                return;
            }

            const typeLabels = {
                stock: 'A股', etf: 'ETF', fund: '基金', stock_hk: '港股'
            };

            quoteCard.innerHTML = `
                <div class="quote-header">
                    <div>
                        <div class="quote-name">${quote.name}</div>
                        <div class="quote-code">${quote.code}</div>
                    </div>
                    <span class="quote-type-badge type-${type}">${typeLabels[type] || type}</span>
                </div>
                <div class="quote-price-main">
                    <div class="quote-price ${quote.change_pct >= 0 ? 'up' : 'down'}">${quote.price.toFixed(2)}</div>
                    <div class="quote-change ${quote.change_pct >= 0 ? 'up' : 'down'}">
                        ${quote.change_pct >= 0 ? '+' : ''}${quote.change_pct.toFixed(2)}%
                        ${quote.change !== undefined ? ` (${quote.change >= 0 ? '+' : ''}${quote.change.toFixed(2)})` : ''}
                    </div>
                </div>
                <div class="quote-details">
                    <div class="quote-detail-item">
                        <span class="quote-detail-label">今开</span>
                        <span class="quote-detail-value">${quote.open ? quote.open.toFixed(2) : '--'}</span>
                    </div>
                    <div class="quote-detail-item">
                        <span class="quote-detail-label">最高</span>
                        <span class="quote-detail-value up">${quote.high ? quote.high.toFixed(2) : '--'}</span>
                    </div>
                    <div class="quote-detail-item">
                        <span class="quote-detail-label">昨收</span>
                        <span class="quote-detail-value">${quote.pre_close ? quote.pre_close.toFixed(2) : '--'}</span>
                    </div>
                    <div class="quote-detail-item">
                        <span class="quote-detail-label">最低</span>
                        <span class="quote-detail-value down">${quote.low ? quote.low.toFixed(2) : '--'}</span>
                    </div>
                    <div class="quote-detail-item">
                        <span class="quote-detail-label">成交量</span>
                        <span class="quote-detail-value">${quote.volume ? this.formatVolume(quote.volume) : '--'}</span>
                    </div>
                    <div class="quote-detail-item">
                        <span class="quote-detail-label">成交额</span>
                        <span class="quote-detail-value">${quote.amount ? this.formatAmount(quote.amount) : '--'}</span>
                    </div>
                </div>
            `;

            tradeCard.style.display = 'block';
            document.getElementById('tradePrice').value = quote.price.toFixed(2);
            this.updateTradeAmount();

        } catch (e) {
            quoteCard.innerHTML = `<div class="card-placeholder">加载失败：${e.message}</div>`;
        }
    },

    formatVolume(vol) {
        if (vol >= 100000000) return (vol / 100000000).toFixed(2) + '亿';
        if (vol >= 10000) return (vol / 10000).toFixed(2) + '万';
        return vol.toFixed(0);
    },

    formatAmount(amt) {
        if (amt >= 100000000) return (amt / 100000000).toFixed(2) + '亿';
        if (amt >= 10000) return (amt / 10000).toFixed(2) + '万';
        return amt.toFixed(2);
    },

    updateTradeAmount() {
        const price = parseFloat(document.getElementById('tradePrice').value) || 0;
        const shares = parseInt(document.getElementById('tradeShares').value) || 0;
        const amount = price * shares;
        document.getElementById('tradeAmount').value = amount ? amount.toFixed(2) : '';
    },

    async doTrade() {
        if (!this.currentStock) return;

        const price = parseFloat(document.getElementById('tradePrice').value);
        const shares = parseInt(document.getElementById('tradeShares').value);

        if (!price || !shares || shares <= 0) {
            this.showToast('请输入有效的价格和数量', 'error');
            return;
        }

        try {
            await API.createTrade({
                code: this.currentStock.code,
                name: this.currentStock.name,
                type: this.currentStock.type,
                action: this.tradeAction,
                price: price,
                shares: shares,
                amount: price * shares,
            });
            this.showToast(`${this.tradeAction === 'buy' ? '买入' : '卖出'}成功！`, 'success');
            document.getElementById('tradeShares').value = '';
            document.getElementById('tradeAmount').value = '';
            this.loadTabContent('positions');
            this.loadTabContent('trades');
        } catch (e) {
            this.showToast(`交易失败：${e.message}`, 'error');
        }
    },

    async loadAnalysis(code, type) {
        const aiCard = document.getElementById('aiCard');
        const cat = type === 'fund' ? 'fund' : type;

        try {
            const result = await API.getAnalysis(code, cat);
            const recLabels = { buy: '买入', sell: '卖出', hold: '持有' };
            const riskLabels = { low: '低风险', medium: '中风险', high: '高风险' };

            const score = result.score_detail || {};
            const buyScore = score.buy_score || 0;
            const sellScore = score.sell_score || 0;
            const total = buyScore + sellScore || 1;
            const buyPct = (buyScore / total) * 100;
            const sellPct = (sellScore / total) * 100;

            const indicators = result.indicators || {};
            const buyRatio = result.buy_ratio !== undefined ? result.buy_ratio : 0;
            const sellRatio = result.sell_ratio !== undefined ? result.sell_ratio : 0;
            const warnings = result.warnings || [];
            const keySupport = result.key_support || [];
            const keyResistance = result.key_resistance || [];
            const stopLossPrice = result.stop_loss_price;
            const stopProfitPrice = result.stop_profit_price;
            const sectors = result.sectors || [];

            aiCard.innerHTML = `
                <div class="ai-header">
                    <h3>智能分析</h3>
                    <span class="ai-badge">${result.ai_available ? 'AI分析' : '技术分析'}</span>
                </div>
                <div class="ai-result">
                    <div class="ai-recommendation ${result.recommendation}">
                        <span class="rec-indicator"></span>
                        <span class="rec-text">${recLabels[result.recommendation] || '持有'}</span>
                        <span class="rec-confidence">置信度 ${(result.confidence * 100).toFixed(0)}%</span>
                    </div>

                    <span class="risk-badge ${result.risk_level}">${riskLabels[result.risk_level] || '中风险'}</span>

                    ${result.target_price ? `
                    <div class="target-price">
                        目标价格：<span class="target-value">${result.target_price.toFixed(2)}</span>
                    </div>
                    ` : ''}

                    ${sectors.length > 0 ? `
                    <div class="ai-sectors">
                        <span class="ai-sectors-label">所属行业：</span>
                        ${sectors.map(s => `<span class="ai-sector-tag">${s}</span>`).join('')}
                    </div>
                    ` : ''}

                    <div class="ai-buy-sell-ratios">
                        <div class="ai-ratio-item">
                            <div class="ai-ratio-label">
                                <span>建议加仓率</span>
                                <span class="ai-ratio-value">${(buyRatio * 100).toFixed(0)}%</span>
                            </div>
                            <div class="ai-ratio-bar">
                                <div class="ai-ratio-fill buy" style="width: ${Math.min(100, buyRatio * 100)}%"></div>
                            </div>
                        </div>
                        <div class="ai-ratio-item">
                            <div class="ai-ratio-label">
                                <span>建议卖出率</span>
                                <span class="ai-ratio-value">${(sellRatio * 100).toFixed(0)}%</span>
                            </div>
                            <div class="ai-ratio-bar">
                                <div class="ai-ratio-fill sell" style="width: ${Math.min(100, sellRatio * 100)}%"></div>
                            </div>
                        </div>
                    </div>

                    <div class="score-bar-container">
                        <div class="score-bar-title">
                            <span>多空评分</span>
                            <span class="score-score">${score.net_score || 0} 分</span>
                        </div>
                        <div class="score-bar">
                            <div class="score-buy" style="width: ${buyPct}%"></div>
                            <div class="score-sell" style="width: ${sellPct}%"></div>
                        </div>
                    </div>

                    ${warnings.length > 0 ? `
                    <div class="ai-warnings">
                        <div class="ai-warnings-title">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path>
                                <line x1="12" y1="9" x2="12" y2="13"></line>
                                <line x1="12" y1="17" x2="12.01" y2="17"></line>
                            </svg>
                            注意事项
                        </div>
                        <ul class="ai-warnings-list">
                            ${warnings.map(w => `<li>${w}</li>`).join('')}
                        </ul>
                    </div>
                    ` : ''}

                    <div class="ai-price-levels">
                        ${keySupport.length > 0 ? `
                        <div class="ai-price-level-item">
                            <div class="ai-price-level-label">关键支撑位</div>
                            <div class="ai-price-level-values">
                                ${keySupport.map(p => `<span class="ai-price-tag support">${p.toFixed(2)}</span>`).join('')}
                            </div>
                        </div>
                        ` : ''}
                        ${keyResistance.length > 0 ? `
                        <div class="ai-price-level-item">
                            <div class="ai-price-level-label">关键阻力位</div>
                            <div class="ai-price-level-values">
                                ${keyResistance.map(p => `<span class="ai-price-tag resistance">${p.toFixed(2)}</span>`).join('')}
                            </div>
                        </div>
                        ` : ''}
                        ${stopLossPrice !== undefined ? `
                        <div class="ai-price-level-item">
                            <div class="ai-price-level-label">止损价</div>
                            <div class="ai-price-level-values">
                                <span class="ai-price-tag stop-loss">${stopLossPrice.toFixed(2)}</span>
                            </div>
                        </div>
                        ` : ''}
                        ${stopProfitPrice !== undefined ? `
                        <div class="ai-price-level-item">
                            <div class="ai-price-level-label">止盈价</div>
                            <div class="ai-price-level-values">
                                <span class="ai-price-tag stop-profit">${stopProfitPrice.toFixed(2)}</span>
                            </div>
                        </div>
                        ` : ''}
                    </div>

                    <div class="indicators-panel">
                        <div class="indicators-title">技术指标</div>
                        <div class="indicators-grid">
                            <div class="indicator-item">
                                <div class="indicator-label">MA5</div>
                                <div class="indicator-value">${indicators.ma5 ? indicators.ma5.toFixed(2) : '--'}</div>
                            </div>
                            <div class="indicator-item">
                                <div class="indicator-label">MA20</div>
                                <div class="indicator-value">${indicators.ma20 ? indicators.ma20.toFixed(2) : '--'}</div>
                            </div>
                            <div class="indicator-item">
                                <div class="indicator-label">MACD</div>
                                <div class="indicator-value">${indicators.macd ? indicators.macd.toFixed(4) : '--'}</div>
                            </div>
                            <div class="indicator-item">
                                <div class="indicator-label">RSI(14)</div>
                                <div class="indicator-value">${indicators.rsi ? indicators.rsi.toFixed(1) : '--'}</div>
                            </div>
                            <div class="indicator-item">
                                <div class="indicator-label">KDJ</div>
                                <div class="indicator-value">K${indicators.k ? indicators.k.toFixed(1) : '--'}</div>
                            </div>
                            <div class="indicator-item">
                                <div class="indicator-label">量能</div>
                                <div class="indicator-value">${indicators.vol_trend || '--'}</div>
                            </div>
                        </div>
                    </div>

                    <div class="reasons-section">
                        <div class="reasons-title buy">买入理由</div>
                        <ul class="reasons-list">
                            ${(result.buy_reasons || ['暂无']).map(r => `<li>${r}</li>`).join('')}
                        </ul>
                    </div>

                    <div class="reasons-section">
                        <div class="reasons-title sell">卖出风险</div>
                        <ul class="reasons-list">
                            ${(result.sell_reasons || ['暂无']).map(r => `<li>${r}</li>`).join('')}
                        </ul>
                    </div>

                    <div class="ai-reasoning">${result.reasoning || ''}</div>
                </div>
            `;
        } catch (e) {
            aiCard.innerHTML = `
                <div class="ai-header">
                    <h3>AI 智能分析</h3>
                    <span class="ai-badge">技术分析</span>
                </div>
                <div class="card-placeholder">分析失败：${e.message}</div>
            `;
        }
    },

    async loadRecommendations() {
        const loadingEl = document.getElementById('recommendLoading');
        const listEl = document.getElementById('recommendList');
        const timeEl = document.getElementById('recommendUpdateTime');
        if (!loadingEl || !listEl) return;

        try {
            const data = await API.getRecommendations();
            this._recommendData = data;
            this.renderRecommendations();

            if (data.updated_at && timeEl) {
                const date = new Date(data.updated_at * 1000);
                timeEl.textContent = '更新时间：' + date.toLocaleTimeString('zh-CN');
            }

            if (data.loading || (!data.stocks?.length && !data.funds?.length)) {
                loadingEl.style.display = 'flex';
                listEl.style.display = 'none';
                this.startRecommendPolling();
            } else {
                loadingEl.style.display = 'none';
                listEl.style.display = 'grid';
            }
        } catch (e) {
            loadingEl.innerHTML = `
                <p style="color: var(--red);">加载失败：${e.message}</p>
                <p class="loading-tip">请刷新页面重试</p>
            `;
        }
    },

    startRecommendPolling() {
        if (this.recommendPollTimer) {
            clearInterval(this.recommendPollTimer);
            this.recommendPollTimer = null;
        }
        let count = 0;
        const maxRetries = 120;
        this.recommendPollTimer = setInterval(async () => {
            count++;
            if (count > maxRetries) {
                clearInterval(this.recommendPollTimer);
                this.recommendPollTimer = null;
                const loadingEl = document.getElementById('recommendLoading');
                if (loadingEl) {
                    loadingEl.innerHTML = `
                        <p style="color: var(--gold);">生成超时，请手动刷新</p>
                        <button class="btn btn-secondary" onclick="App.refreshRecommendations()" style="cursor:pointer;">重新生成</button>
                    `;
                }
                return;
            }
            try {
                const progress = await API.getRecommendProgress();
                const loadingEl = document.getElementById('recommendLoading');
                if (loadingEl && progress.status === 'loading') {
                    const pct = Math.min(100, Math.round(progress.done));
                    const tip = progress.message || '正在分析市场数据...';
                    loadingEl.innerHTML = `
                        <div class="loading-spinner"></div>
                        <p>${tip}</p>
                        <div class="progress-bar">
                            <div class="progress-fill" style="width: ${pct}%"></div>
                        </div>
                        <p class="loading-tip">${pct}% 完成</p>
                    `;
                }

                const data = await API.getRecommendations();
                if (data && (data.stocks?.length || data.funds?.length)) {
                    if (this.recommendPollTimer) {
                        clearInterval(this.recommendPollTimer);
                        this.recommendPollTimer = null;
                    }
                    this._recommendData = data;
                    this.renderRecommendations();
                    const loadingEl2 = document.getElementById('recommendLoading');
                    const listEl = document.getElementById('recommendList');
                    if (loadingEl2) loadingEl2.style.display = 'none';
                    if (listEl) listEl.style.display = 'grid';
                    this.showToast('推荐数据已生成', 'success');
                }
            } catch (e) {
                // ignore polling errors
            }
        }, 2000);
    },

    async refreshRecommendations() {
        const listEl = document.getElementById('recommendList');
        const loadingEl = document.getElementById('recommendLoading');
        if (loadingEl) loadingEl.style.display = 'flex';
        if (listEl) listEl.style.display = 'none';
        this._recommendData = null;

        try {
            await API.refreshRecommendations();
            this.showToast('正在重新生成推荐，请稍候...', 'info');
            this.startRecommendPolling();
        } catch (e) {
            this.showToast('刷新失败：' + e.message, 'error');
        }
    },

    renderRecommendations() {
        const listEl = document.getElementById('recommendList');
        if (!listEl || !this._recommendData) return;

        let items = [];
        if (this.recommendType === 'all') {
            items = [
                ...(this._recommendData.stocks || []),
                ...(this._recommendData.funds || []),
            ].sort((a, b) => b.score - a.score);
        } else if (this.recommendType === 'stock') {
            items = (this._recommendData.stocks || []).slice().sort((a, b) => b.score - a.score);
        } else if (this.recommendType === 'fund') {
            items = (this._recommendData.funds || []).slice().sort((a, b) => b.score - a.score);
        }

        // 按风险类型过滤
        if (this.recommendRiskTier !== 'all') {
            items = items.filter(item => item.risk_tier === this.recommendRiskTier);
        }

        if (items.length === 0) {
            listEl.innerHTML = '<div style="grid-column: 1/-1; text-align: center; padding: 60px 20px; color: var(--text-muted);">暂无符合条件的推荐<br><small>试试切换风险类型筛选</small></div>';
            return;
        }

        const typeLabels = { stock: '股票', etf: 'ETF/基金', fund: '基金' };
        const riskLabels = { low: '低风险', medium: '中风险', high: '高风险' };
        const strengthColors = {
            '强势推荐': 'linear-gradient(135deg, #ef4444, #f97316)',
            '推荐': 'linear-gradient(135deg, #f59e0b, #eab308)',
            '关注': 'linear-gradient(135deg, #3b82f6, #6366f1)',
        };

        listEl.innerHTML = items.map((item, idx) => {
            const rankClass = idx === 0 ? '' : idx === 1 ? 'rank-2' : idx === 2 ? 'rank-3' : 'rank-other';
            const scorePct = Math.min(100, Math.max(0, (item.score / 12) * 100));
            const strength = item.strength || '关注';
            const strengthGrad = strengthColors[strength] || strengthColors['关注'];
            const upsidePct = item.upside_pct || 0;
            const targetPrice = item.target_price || 0;
            const gap = targetPrice > 0 ? targetPrice - item.price : 0;
            const gapPct = targetPrice > 0 ? ((targetPrice - item.price) / item.price * 100) : 0;
            const riskItems = item.sell_reasons || [];
            const riskLevel = item.risk_level || 'medium';
            const riskLevelLabels = { low: '低风险', medium: '中风险', high: '高风险' };

            return `
            <div class="recommend-card" data-code="${item.code}" data-type="${item.type}" data-name="${item.name}">
                <div class="rec-rank ${rankClass}">${idx + 1}</div>
                <div class="rec-strength-badge" style="background: ${strengthGrad}">${strength}</div>
                <div class="rec-card-header">
                    <div>
                        <div class="rec-card-name">${item.name}</div>
                        <div class="rec-card-code">${item.code}</div>
                    </div>
                    <span class="rec-card-type type-${item.type}">${typeLabels[item.type] || item.type}</span>
                </div>
                <div class="rec-card-price">
                    <span class="rec-price-label">现价</span>
                    <span class="rec-price ${item.change_pct >= 0 ? 'up' : 'down'}">${item.price.toFixed(2)}</span>
                    <span class="rec-change ${item.change_pct >= 0 ? 'up' : 'down'}">${item.change_pct >= 0 ? '+' : ''}${item.change_pct.toFixed(2)}%</span>
                    ${targetPrice > 0 ? `
                    <span class="rec-target-label">目标价</span>
                    <span class="rec-target">${targetPrice.toFixed(2)}</span>
                    <span class="rec-gap">价差 ${gap >= 0 ? '+' : ''}${gap.toFixed(2)} (${gapPct >= 0 ? '+' : ''}${gapPct.toFixed(1)}%)</span>
                    ` : ''}
                    ${upsidePct > 0 && targetPrice <= 0 ? `<span class="rec-upside">目标空间 +${upsidePct.toFixed(1)}%</span>` : ''}
                </div>
                <div class="rec-card-score">
                    <div class="rec-score-header">
                        <span class="rec-score-label">综合评分</span>
                        <span class="rec-score-value">${item.score}分</span>
                    </div>
                    <div class="rec-score-bar">
                        <div class="rec-score-fill" style="width: ${scorePct}%"></div>
                    </div>
                    <div class="rec-score-detail">
                        <span class="score-buy">多头 ${item.buy_score || 0}</span>
                        <span class="score-sell">空头 ${item.sell_score || 0}</span>
                        <span class="score-conf">置信度 ${(item.confidence * 100).toFixed(0)}%</span>
                    </div>
                </div>
                <div class="rec-card-reason">
                    <div class="rec-reason-title">推荐理由</div>
                    <ul class="rec-reason-list">
                        ${(item.buy_reasons || ['暂无详细理由']).slice(0, 3).map(r => `<li>${r}</li>`).join('')}
                    </ul>
                </div>
                ${riskItems.length > 0 ? `
                <div class="rec-card-risk">
                    <div class="rec-risk-title">风险提示</div>
                    <ul class="rec-risk-list">
                        ${riskItems.slice(0, 2).map(r => `<li>${r}</li>`).join('')}
                    </ul>
                    <div class="rec-risk-detail">
                        <div class="rec-risk-detail-item">行业风险：${riskLevelLabels[riskLevel] || '中风险'}级别</div>
                        <div class="rec-risk-detail-item">估值风险：需关注市场估值变化</div>
                        <div class="rec-risk-detail-item">波动率风险：注意短期波动影响</div>
                    </div>
                </div>
                ` : `
                <div class="rec-card-risk">
                    <div class="rec-risk-title">风险提示</div>
                    <div class="rec-risk-detail">
                        <div class="rec-risk-detail-item">行业风险：${riskLevelLabels[riskLevel] || '中风险'}级别</div>
                        <div class="rec-risk-detail-item">估值风险：需关注市场估值变化</div>
                        <div class="rec-risk-detail-item">波动率风险：注意短期波动影响</div>
                    </div>
                </div>
                `}
                <div class="rec-card-footer">
                    <div class="rec-footer-left">
                        <span class="rec-tier-badge tier-${item.risk_tier || '保守型'}">${item.risk_tier || '保守型'}</span>
                        <span class="rec-risk-badge ${riskLevel}">${riskLevelLabels[riskLevel] || '中风险'}</span>
                    </div>
                    <span class="rec-card-target">目标价：<span>${targetPrice > 0 ? targetPrice.toFixed(2) : '--'}</span></span>
                </div>
            </div>
            `;
        }).join('');

        listEl.querySelectorAll('.recommend-card').forEach(el => {
            el.addEventListener('click', () => {
                const code = el.dataset.code;
                const name = el.dataset.name;
                const type = el.dataset.type;
                this.selectQuote(code, name, type);
            });
        });
    },

    async loadMarketIndex() {
        const el = document.getElementById('marketIndices');
        try {
            const indices = await API.getMarketIndex();
            el.innerHTML = Object.entries(indices).map(([name, data]) => `
                <div class="market-index">
                    <span class="market-index-name">${name}</span>
                    <span class="market-index-price ${data.change_pct >= 0 ? 'up' : 'down'}">
                        ${data.price.toFixed(2)} (${data.change_pct >= 0 ? '+' : ''}${data.change_pct.toFixed(2)}%)
                    </span>
                </div>
            `).join('');
        } catch (e) {
            el.innerHTML = '<span class="index-loading">指数加载失败</span>';
        }
    },

    loadTabContent(tab) {
        if (tab === 'positions') this.loadPositions();
        if (tab === 'trades') this.loadTrades();
        if (tab === 'watchlist') this.loadWatchlist();
    },

    async loadPositions() {
        const table = document.querySelector('#positionsTable tbody');
        const summary = document.getElementById('positionsSummary');
        const monitorPanel = document.getElementById('positionMonitor');
        if (!table) return;

        try {
            const data = await API.getPositions();
            const positions = data.positions;

            if (positions.length === 0) {
                table.innerHTML = '<tr><td colspan="9" style="text-align:center; padding: 40px; color: var(--text-muted);">暂无持仓</td></tr>';
                summary.innerHTML = `
                    <div class="summary-item"><div class="summary-label">总资产</div><div class="summary-value">¥0.00</div></div>
                    <div class="summary-item"><div class="summary-label">持仓市值</div><div class="summary-value">¥0.00</div></div>
                    <div class="summary-item"><div class="summary-label">可用资金</div><div class="summary-value">¥0.00</div></div>
                    <div class="summary-item"><div class="summary-label">总盈亏</div><div class="summary-value">¥0.00</div></div>
                `;
                if (monitorPanel) monitorPanel.innerHTML = '';
                return;
            }

            const totalMarketValue = positions.reduce((sum, p) => sum + (p.market_value || 0), 0);
            const totalProfit = positions.reduce((sum, p) => sum + (p.profit || 0), 0);
            const typeLabels = { stock: '股票', etf: 'ETF', fund: '基金', stock_hk: '港股' };
            const actionColors = { '持有': '#3b82f6', '减仓': '#f59e0b', '清仓': '#ef4444', '止盈': '#22c55e', '止损': '#ef4444' };

            table.innerHTML = positions.map(p => `
                <tr data-code="${p.code}" data-type="${p.type}">
                    <td>${p.code}</td>
                    <td>${p.name}</td>
                    <td><span class="search-result-type type-${p.type}">${typeLabels[p.type] || p.type}</span></td>
                    <td>${p.shares}</td>
                    <td>${(p.avg_cost || 0).toFixed(2)}</td>
                    <td class="${p.current_price >= (p.avg_cost || 0) ? 'up' : 'down'}">${p.current_price.toFixed(2)}</td>
                    <td>${p.market_value.toFixed(2)}</td>
                    <td class="${p.profit >= 0 ? 'up' : 'down'}">${p.profit >= 0 ? '+' : ''}${p.profit.toFixed(2)}</td>
                    <td class="${p.profit_pct >= 0 ? 'up' : 'down'}">${p.profit_pct >= 0 ? '+' : ''}${p.profit_pct.toFixed(2)}%</td>
                </tr>
            `).join('');

            summary.innerHTML = `
                <div class="summary-item">
                    <div class="summary-label">总资产</div>
                    <div class="summary-value">¥${(data.total_assets || 0).toFixed(2)}</div>
                </div>
                <div class="summary-item">
                    <div class="summary-label">持仓市值</div>
                    <div class="summary-value">¥${totalMarketValue.toFixed(2)}</div>
                </div>
                <div class="summary-item">
                    <div class="summary-label">可用资金</div>
                    <div class="summary-value">¥${(data.available_cash || 0).toFixed(2)}</div>
                </div>
                <div class="summary-item">
                    <div class="summary-label">总盈亏</div>
                    <div class="summary-value ${totalProfit >= 0 ? 'up' : 'down'}">${totalProfit >= 0 ? '+' : ''}¥${totalProfit.toFixed(2)}</div>
                </div>
            `;

            // 渲染持仓监控面板
            if (monitorPanel) {
                const monitorData = positions.filter(p => p.monitor).map(p => p.monitor);
                if (monitorData.length > 0) {
                    monitorPanel.innerHTML = `
                        <div class="monitor-title">持仓实时监控</div>
                        ${positions.map(p => {
                            const m = p.monitor || {};
                            const actionColor = actionColors[m.action] || '#3b82f6';
                            const upsidePct = m.upside_pct || 0;
                            const upsideColor = upsidePct > 10 ? '#22c55e' : upsidePct > 5 ? '#f59e0b' : '#ef4444';
                            return `
                            <div class="monitor-item" data-code="${p.code}">
                                <div class="monitor-header">
                                    <span class="monitor-name">${p.name}</span>
                                    <span class="monitor-action" style="background:${actionColor}">${m.action || '持有'}</span>
                                </div>
                                <div class="monitor-prices">
                                    <span>现价 <strong>${m.current_price || p.current_price}</strong></span>
                                    <span>目标 <strong>${m.target_price || '--'}</strong></span>
                                    <span style="color:${upsideColor}">空间 <strong>${upsidePct > 0 ? '+' : ''}${upsidePct}%</strong></span>
                                </div>
                                ${m.sell_signal ? `
                                <div class="monitor-alert">
                                    <div class="monitor-alert-icon">⚠️</div>
                                    <div class="monitor-alert-text">
                                        <div class="monitor-signal">${m.sell_signal}</div>
                                        ${(m.sell_reasons || []).map(r => `<div class="monitor-reason">• ${r}</div>`).join('')}
                                    </div>
                                </div>
                                ` : ''}
                                ${(m.hold_reasons || []).length > 0 ? `
                                <div class="monitor-hold-reasons">
                                    ${(m.hold_reasons || []).map(r => `<div class="monitor-reason hold">• ${r}</div>`).join('')}
                                </div>
                                ` : ''}
                                ${m.indicators && Object.keys(m.indicators).length > 0 ? `
                                <div class="monitor-indicators">
                                    <span>RSI ${m.indicators.rsi || '--'}</span>
                                    <span>MACD ${m.indicators.macd || '--'}</span>
                                    <span>K ${m.indicators.kdj_k || '--'} D ${m.indicators.kdj_d || '--'}</span>
                                </div>
                                ` : ''}
                            </div>
                            `;
                        }).join('')}
                    `;
                } else {
                    monitorPanel.innerHTML = '';
                }
            }

            table.querySelectorAll('tr').forEach(tr => {
                tr.addEventListener('click', () => {
                    const code = tr.dataset.code;
                    const type = tr.dataset.type;
                    const name = tr.querySelector('td:nth-child(2)').textContent;
                    this.selectQuote(code, name, type);
                });
            });
        } catch (e) {
            table.innerHTML = `<tr><td colspan="9" style="text-align:center; padding: 40px; color: var(--red);">
                加载失败：${e.message}<br><br>
                <button class="btn btn-secondary" onclick="App.loadPositions()" style="cursor:pointer;">点击重试</button>
            </td></tr>`;
        }
    },

    async loadTrades() {
        const table = document.querySelector('#tradesTable tbody');
        if (!table) return;

        try {
            const trades = await API.getTrades();
            if (trades.length === 0) {
                table.innerHTML = '<tr><td colspan="8" style="text-align:center; padding: 40px; color: var(--text-muted);">暂无交易记录</td></tr>';
                return;
            }

            const typeLabels = { stock: '股票', etf: 'ETF', fund: '基金', stock_hk: '港股' };
            const actionLabels = { buy: '买入', sell: '卖出' };

            table.innerHTML = trades.map(t => `
                <tr>
                    <td>${t.created_at}</td>
                    <td>${t.code}</td>
                    <td>${t.name}</td>
                    <td><span class="search-result-type type-${t.type}">${typeLabels[t.type] || t.type}</span></td>
                    <td class="${t.action === 'buy' ? 'up' : 'down'}">${actionLabels[t.action] || t.action}</td>
                    <td>${t.shares}</td>
                    <td>${t.price.toFixed(2)}</td>
                    <td>¥${t.amount.toFixed(2)}</td>
                </tr>
            `).join('');
        } catch (e) {
            table.innerHTML = `<tr><td colspan="8" style="text-align:center; padding: 40px; color: var(--red);">加载失败：${e.message}</td></tr>`;
        }
    },

    async loadWatchlist() {
        const table = document.querySelector('#watchlistTable tbody');
        if (!table) return;
        // 简单实现
        table.innerHTML = '<tr><td colspan="6" style="text-align:center; padding: 40px; color: var(--text-muted);">暂无自选</td></tr>';
    },

    async checkVersion(manual = false) {
        try {
            const data = await API.checkVersion();
            document.getElementById('versionText').textContent = 'v' + data.currentVersion;

            const badge = document.getElementById('updateBadge');
            if (data.hasUpdate) {
                badge.classList.add('show');
                if (manual) {
                    this._showUpdateDialog(data);
                }
            } else if (manual) {
                this.showToast('当前已是最新版本', 'success');
            }
        } catch (e) {
            if (manual) this.showToast('检查更新失败', 'error');
        }
    },

    _showUpdateDialog(data) {
        const overlay = document.createElement('div');
        overlay.className = 'update-dialog-overlay';
        overlay.innerHTML = `
            <div class="update-dialog">
                <h3>发现新版本</h3>
                <div class="update-version">
                    <span class="new">v${data.latestVersion}</span>
                    <span class="arrow">→</span>
                    <span class="old">v${data.currentVersion}</span>
                </div>
                <div class="update-notes">${data.releaseNotes || '暂无更新说明'}</div>
                <div class="update-dialog-actions">
                    <button class="btn btn-secondary" id="updateCancel">稍后</button>
                    <button class="btn btn-primary" id="updateNow">立即更新</button>
                </div>
            </div>
        `;
        document.body.appendChild(overlay);

        overlay.querySelector('#updateCancel').addEventListener('click', () => overlay.remove());
        overlay.querySelector('#updateNow').addEventListener('click', () => {
            if (data.downloadUrl) {
                window.open(data.downloadUrl, '_blank');
            }
            overlay.remove();
        });
    },

    pollDataStatus() {
        setInterval(() => {
            if (this.currentStock) {
                const type = this.currentStock.type;
                const code = this.currentStock.code;
                if (type !== 'fund') {
                    API.getStockQuote(code).then(q => {
                        if (q) {
                            const priceEl = document.querySelector('.quote-price');
                            if (priceEl) {
                                priceEl.textContent = q.price.toFixed(2);
                                priceEl.className = 'quote-price ' + (q.change_pct >= 0 ? 'up' : 'down');
                            }
                        }
                    }).catch(() => {});
                }
            }
        }, 5000);
    },

    showToast(message, type = 'info') {
        let container = document.querySelector('.toast-container');
        if (!container) {
            container = document.createElement('div');
            container.className = 'toast-container';
            document.body.appendChild(container);
        }
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.textContent = message;
        container.appendChild(toast);
        setTimeout(() => toast.remove(), 3000);
    },

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    },

    formatMessage(text) {
        let html = this.escapeHtml(text);
        html = html.replace(/\n/g, '<br>');
        html = html.replace(/```(\w+)?\n([\s\S]*?)```/g, (match, lang, code) => {
            return `<pre class="chat-code-block"><code>${code.trim()}</code></pre>`;
        });
        html = html.replace(/`([^`]+)`/g, (match, code) => {
            return `<code class="chat-inline-code">${code}</code>`;
        });
        return html;
    },

    async sendChatMessage() {
        const chatInput = document.getElementById('chatInput');
        const message = chatInput.value.trim();

        if (!message) {
            this.showToast('请输入消息内容', 'warning');
            return;
        }

        if (this.isChatLoading) {
            return;
        }

        this.isChatLoading = true;
        this.chatMessages.push({ role: 'user', content: message });
        chatInput.value = '';
        this.renderChatMessages();

        try {
            const context = this.currentStock ? {
                code: this.currentStock.code,
                name: this.currentStock.name,
                type: this.currentStock.type,
            } : {};

            const response = await API.chatSend(message, context);
            if (response && response.reply) {
                this.chatMessages.push({ role: 'assistant', content: response.reply });
            } else {
                this.chatMessages.push({ role: 'assistant', content: '抱歉，AI 暂时无法回复，请稍后再试。' });
            }
        } catch (e) {
            this.chatMessages.push({ role: 'assistant', content: `发送失败：${e.message}` });
        } finally {
            this.isChatLoading = false;
            this.renderChatMessages();
        }
    },

    renderChatMessages() {
        const chatMessagesEl = document.getElementById('chatMessages');
        if (!chatMessagesEl) return;

        if (this.chatMessages.length === 0) {
            chatMessagesEl.innerHTML = `
                <div class="chat-placeholder">
                    <div class="chat-placeholder-icon">
                        <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
                        </svg>
                    </div>
                    <h3>AI 智能助手</h3>
                    <p>选择一只股票或基金后，开始与 AI 对话</p>
                    <p class="chat-tip">支持技术分析、投资建议、行业研究等问题</p>
                </div>
            `;
            return;
        }

        chatMessagesEl.innerHTML = this.chatMessages.map((msg, idx) => {
            const isUser = msg.role === 'user';
            const isLoading = idx === this.chatMessages.length - 1 && this.isChatLoading && !isUser;
            return `
                <div class="chat-message ${isUser ? 'user' : 'assistant'}">
                    <div class="chat-message-avatar">
                        ${isUser ? '👤' : '🤖'}
                    </div>
                    <div class="chat-message-content">
                        ${isLoading ? '<div class="chat-typing"><span></span><span></span><span></span></div>' : this.formatMessage(msg.content)}
                    </div>
                </div>
            `;
        }).join('');

        if (this.isChatLoading) {
            const loadingMsg = document.createElement('div');
            loadingMsg.className = 'chat-message assistant';
            loadingMsg.innerHTML = `
                <div class="chat-message-avatar">🤖</div>
                <div class="chat-message-content">
                    <div class="chat-typing"><span></span><span></span><span></span></div>
                </div>
            `;
            chatMessagesEl.appendChild(loadingMsg);
        }

        chatMessagesEl.scrollTop = chatMessagesEl.scrollHeight;
    },

    updateChatContext() {
        const contextEl = document.getElementById('chatContext');
        if (!contextEl) return;

        if (!this.currentStock) {
            contextEl.innerHTML = '<div class="chat-context-empty">暂无选中标的</div>';
            return;
        }

        const typeLabels = { stock: '股票', etf: 'ETF', fund: '基金', stock_hk: '港股' };
        const stock = this.currentStock;

        contextEl.innerHTML = `
            <div class="chat-context-item">
                <div class="chat-context-name">${stock.name}</div>
                <div class="chat-context-code">${stock.code}</div>
                <span class="chat-context-type type-${stock.type}">${typeLabels[stock.type] || stock.type}</span>
            </div>
            <div class="chat-context-tip">
                AI 将基于此标的信息进行分析回答
            </div>
        `;
    },

    async clearChatHistory() {
        try {
            await API.chatClear();
        } catch (e) {
            // ignore
        }
        this.chatMessages = [];
        this.renderChatMessages();
        this.showToast('聊天记录已清除', 'success');
    },
};

document.addEventListener('DOMContentLoaded', () => App.init());
