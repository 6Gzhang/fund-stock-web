// API 请求封装
const API = {
    _pendingSearch: null, // 用于取消上一次搜索请求

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
        // 取消上一次未完成的搜索请求
        if (this._pendingSearch) {
            this._pendingSearch.abort();
        }
        this._pendingSearch = new AbortController();
        try {
            const result = await this.get('/search', { keyword, category }, this._pendingSearch.signal);
            return result;
        } finally {
            if (this._pendingSearch && this._pendingSearch.signal.aborted === false) {
                // 只有当前请求完成时才清除（避免被新请求覆盖）
            }
        }
    },

    async getQuote(code, category) {
        return this.get(`/quote/${code}`, { category });
    },

    async getHistory(code, category, days = 90) {
        return this.get(`/history/${code}`, { category, days });
    },

    async getMarketIndex() {
        return this.get('/market-index');
    },

    async executeTrade(data) {
        return this.post('/trade/execute', data);
    },

    async getPositions() {
        return this.get('/trade/positions');
    },

    async getTrades(limit = 50) {
        return this.get('/trade/trades', { limit });
    },

    async getWatchlist() {
        return this.get('/trade/watchlist');
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

    async getAIStatus() {
        return this.get('/analysis/status');
    },

    async getVersion() {
        return this.get('/version');
    },
};