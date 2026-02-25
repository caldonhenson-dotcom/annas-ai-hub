/* ============================================================
   Skills Engine — execution, progress, results, error handling
   ============================================================ */
(function () {
    'use strict';

    var _running = {};
    var HISTORY_KEY = 'ecomplete_skill_history';
    var MAX_HISTORY = 50;

    function isRunning(skillId) { return !!_running[skillId]; }

    function validateInputs(skill, values) {
        var errors = [];
        (skill.execute.inputs || []).forEach(function (inp) {
            if (inp.required && !values[inp.key]) errors.push(inp.label + ' is required');
        });
        return errors;
    }

    function _emit(skillId, status, message) {
        document.dispatchEvent(new CustomEvent('skill-progress', {
            detail: { skillId: skillId, status: status, message: message, timestamp: Date.now() }
        }));
    }

    function _loadHistory() {
        try { return JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]'); } catch (e) { return []; }
    }
    function _record(skillId, success, dur) {
        var h = _loadHistory();
        h.push({ skillId: skillId, timestamp: Date.now(), success: success, durationMs: dur });
        if (h.length > MAX_HISTORY) h = h.slice(-MAX_HISTORY);
        try { localStorage.setItem(HISTORY_KEY, JSON.stringify(h)); } catch (e) { /* empty */ }
    }

    // Shared fetch wrapper: start tracking, fetch, handle success/error, clean up
    function _run(skill, msg, url, payload, resultType, extractData) {
        var exec = skill.execute;
        var controller = new AbortController();
        var start = Date.now();
        _running[skill.id] = { controller: controller, start: start };
        _emit(skill.id, 'running', msg);
        return fetch(url, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload), signal: controller.signal
        })
        .then(function (r) {
            if (!r.ok) return r.json().then(function (d) { throw new Error(d.error || 'Request failed'); });
            return r.json();
        })
        .then(function (data) {
            var dur = Date.now() - start;
            _emit(skill.id, 'complete', 'Done in ' + (dur / 1000).toFixed(1) + 's');
            _record(skill.id, true, dur);
            if (data.usage && window.APIConfig) window.APIConfig.addTokens(data.usage.input_tokens || 0, data.usage.output_tokens || 0);
            return { type: resultType || exec.resultType || 'markdown', data: extractData(data), actions: exec.actions || [] };
        })
        .catch(function (err) {
            _emit(skill.id, 'error', err.message);
            _record(skill.id, false, Date.now() - start);
            throw err;
        })
        .finally(function () { delete _running[skill.id]; });
    }

    function execute(skillId, inputValues) {
        var skill = window.SkillsRegistry.get(skillId);
        if (!skill) return Promise.reject(new Error('Skill not found: ' + skillId));
        if (isRunning(skillId)) return Promise.reject(new Error('Already running'));
        var errors = validateInputs(skill, inputValues || {});
        if (errors.length > 0) return Promise.reject(new Error(errors.join(', ')));
        var exec = skill.execute;
        switch (exec.type) {
            case 'ai-query':      return _execAiQuery(skill, inputValues);
            case 'ai-structured': return _execProxy(skill, inputValues, 'structured', 'Running AI analysis...');
            case 'api-call':      return _execProxy(skill, inputValues, 'api-call', 'Calling API...');
            case 'multi-step':    return _execMultiStep(skill, inputValues);
            case 'draft':         return _execDraft(skill, inputValues);
            case 'client-only':   return _execClient(skill, inputValues);
            default: return Promise.reject(new Error('Unknown type: ' + exec.type));
        }
    }

    // AI Query handler (existing /api/ai-query or /api/claude-query)
    function _execAiQuery(skill, inputs) {
        var exec = skill.execute;
        var endpoint = exec.endpoint || window.getApiEndpoint();
        var raw = exec.buildPayload(inputs);
        var payload = window.buildPayload ? window.buildPayload(raw.question || raw.prompt, [], raw) : raw;
        return _run(skill, 'Sending to AI...', endpoint, payload, null, function (d) {
            return d.answer || d.response || d;
        });
    }

    // Structured + API Call proxy via /api/skill-execute
    function _execProxy(skill, inputs, type, msg) {
        var payload = skill.execute.buildPayload(inputs);
        payload._skillId = skill.id;
        payload._type = type;
        var rt = type === 'structured' ? 'json' : null;
        return _run(skill, msg, '/api/skill-execute', payload, rt, function (d) {
            return d.result || d;
        });
    }

    // Multi-step orchestration (chained client-side calls)
    function _execMultiStep(skill, inputs) {
        var exec = skill.execute;
        var steps = exec.steps || [];
        var controller = new AbortController();
        var start = Date.now();
        _running[skill.id] = { controller: controller, start: start };
        return steps.reduce(function (chain, step, idx) {
            return chain.then(function (prev) {
                if (controller.signal.aborted) throw new Error('Cancelled');
                _emit(skill.id, 'running', 'Step ' + (idx + 1) + '/' + steps.length + ': ' + step.label);
                return fetch(step.endpoint, {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(step.buildPayload(inputs, prev)), signal: controller.signal
                }).then(function (r) { return r.json(); });
            });
        }, Promise.resolve(null))
        .then(function (final) {
            var dur = Date.now() - start;
            _emit(skill.id, 'complete', 'All steps complete');
            _record(skill.id, true, dur);
            return { type: exec.resultType || 'markdown', data: final, actions: exec.actions || [] };
        })
        .catch(function (err) { _emit(skill.id, 'error', err.message); _record(skill.id, false, Date.now() - start); throw err; })
        .finally(function () { delete _running[skill.id]; });
    }

    // Draft handler (reuses /api/draft-message)
    function _execDraft(skill, inputs) {
        var payload = skill.execute.buildPayload(inputs);
        return _run(skill, 'Drafting...', '/api/draft-message', payload, 'draft', function (d) {
            return d.draft || d.message || d;
        });
    }

    // Client-only (no API call)
    function _execClient(skill, inputs) {
        var start = Date.now();
        _emit(skill.id, 'running', 'Executing...');
        try {
            var result = skill.execute.run(inputs);
            _emit(skill.id, 'complete', 'Done');
            _record(skill.id, true, Date.now() - start);
            return Promise.resolve({ type: 'action-confirm', data: result, actions: [] });
        } catch (err) {
            _emit(skill.id, 'error', err.message); _record(skill.id, false, Date.now() - start);
            return Promise.reject(err);
        }
    }

    function cancel(skillId) {
        if (_running[skillId] && _running[skillId].controller) {
            _running[skillId].controller.abort(); _emit(skillId, 'cancelled', 'Cancelled');
            delete _running[skillId];
        }
    }

    var _handlers = {
        copyResult: function (skill, result) {
            var text = typeof result.data === 'string' ? result.data : JSON.stringify(result.data, null, 2);
            navigator.clipboard.writeText(text).then(function () {
                if (window.Notifications) window.Notifications.show('Copied to clipboard', 'success');
            });
        },
        exportPdf: function (skill, result) {
            var w = window.open('', '_blank');
            if (!w) return;
            var html = typeof result.data === 'string' ? result.data : JSON.stringify(result.data, null, 2);
            w.document.write('<html><head><title>' + skill.name + '</title>'
                + '<style>body{font-family:system-ui;max-width:800px;margin:40px auto;padding:0 20px;line-height:1.6}'
                + 'pre{background:#f3f4f6;padding:12px;border-radius:8px;overflow-x:auto}</style></head>'
                + '<body><h1>' + skill.name + '</h1><div>' + html.replace(/\n/g, '<br>') + '</div></body></html>');
            w.document.close(); w.print();
        }
    };

    window.SkillsEngine = {
        execute: execute, cancel: cancel, isRunning: isRunning,
        getHistory: _loadHistory,
        handleResultAction: function (h, s, r) { if (_handlers[h]) _handlers[h](s, r); }
    };
})();
