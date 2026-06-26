// API 请求封装 - 统一安全处理所有返回值
const API = {
    _pendingSearch: null,

    async get(url, params = {}, signal = null) {
        const query = new URLSearchParams(params).toString();
        const res = await fetch(`/api${url}${query ? '?' + query : ''}`, { signal });
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: '请求失败' }));
            throw new Error(err.detail || '请求失败');
        }
        return res.json();
    },

    async post(url, data = {}, params = {}) {
        const query = new URLSearchParams(params).toString();
        const fullUrl = `/api${url}${query ? '?' + query : ''}`;
        const res = await fetch(fullUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: '请求失败' }));
            throw new Error(err.detail || '请求失败');
        }
        return res.json();
    },

    async search(keyword, category = 'all') {
        if (this._pendingSearch) {
            this._pendingSearch.abort();
        }
        this._pendingSearch = new AbortController();
        try {
            const result = await this.get('/search', { keyword, category }, this._pendingSearch.signal);
            return (result && result.results) || [];
        } finally {
            this._pendingSearch = null;
        }
    },

    async getQuote(code, category) {
        return this.get(`/quote/${code}`, { category });
    },

    async getHistory(code, category, days = 90) {
        return this.get(`/history/${code}`, { category, days });
    },

    async getMarketIndex() {
        const result = await this.get('/market-index');
        return result || {};
    },

    async executeTrade(data) {
        return this.post('/trade/execute', data);
    },

    async getPositions() {
        const result = await this.get('/trade/positions');
        return {
            positions: (result && result.positions) || [],
            total_assets: (result && result.total_assets) || 0,
            available_cash: (result && result.available_cash) || 0,
            total_market_value: (result && result.total_market_value) || 0,
            total_profit: (result && result.total_profit) || 0,
            total_profit_pct: (result && result.total_profit_pct) || 0,
        };
    },

    async getTrades(limit = 50) {
        const result = await this.get('/trade/trades', { limit });
        return (result && result.trades) || [];
    },

    async getWatchlist() {
        const result = await this.get('/trade/watchlist');
        return (result && result.watchlist) || [];
    },

    async addToWatchlist(code, name, type) {
        return this.post('/trade/watchlist/add', {}, { code, name, type });
    },

    async removeFromWatchlist(code) {
        return this.post('/trade/watchlist/remove', {}, { code });
    },

    async analyzeStock(code, category) {
        return this.get(`/analysis/stock/${code}`, { category });
    },

    async getAnalysis(code, category) {
        return this.get(`/analysis/stock/${code}`, { category });
    },

    async getAIStatus() {
        return this.get('/analysis/status');
    },

    async getRecommendations() {
        const result = await this.get('/analysis/recommendations');
        return {
            stocks: (result && result.stocks) || [],
            funds: (result && result.funds) || [],
            updated_at: (result && result.updated_at) || 0,
            loading: (result && result.loading) || false,
        };
    },

    async getRecommendProgress() {
        try {
            const result = await this.get('/analysis/recommendations/progress');
            return result || { status: 'idle', done: 0, total: 0, message: '' };
        } catch (e) {
            return { status: 'idle', done: 0, total: 0, message: '' };
        }
    },

    async refreshRecommendations() {
        return this.post('/analysis/recommendations/refresh');
    },

    async getStockQuote(code) {
        return this.get(`/quote/${code}`, { category: 'stock' });
    },

    async getFundQuote(code) {
        return this.get(`/quote/${code}`, { category: 'fund' });
    },

    async createTrade(data) {
        return this.post('/trade/execute', data);
    },

    async getVersion() {
        return this.get('/version');
    },

    async checkVersion() {
        const data = await this.get('/version');
        return {
            currentVersion: data.version,
            latestVersion: data.latestVersion,
            hasUpdate: data.hasUpdate,
            downloadUrl: data.downloadUrl,
            releaseNotes: data.releaseNotes,
        };
    },

    async getDataStatus() {
        return this.get('/data-status');
    },
};
