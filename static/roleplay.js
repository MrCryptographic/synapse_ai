(() => {
    const csrfToken = document.querySelector('meta[name="csrf-token"]').content;
    const status = document.getElementById('status');
    let localProfiles = [];
    let libraryProfiles = [];
    let activeSession = null;
    let activeMessages = [];
    let activeGenerationController = null;
    let activeGenerationId = null;
    let outOfCharacterMode = false;
    let modelRatings = new Map();

    async function api(url, options = {}) {
        const headers = { ...options.headers, 'X-CSRF-Token': csrfToken };
        if (options.body && !(options.body instanceof FormData)) {
            headers['Content-Type'] = 'application/json';
        }
        const response = await fetch(url, { ...options, headers });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || `HTTP ${response.status}`);
        return result;
    }

    function setStatus(message, isError = false) {
        status.textContent = message;
        status.style.color = isError ? '#ff9b9b' : '';
    }

    function cardFor(type) {
        return document.querySelector(`[data-profile-type="${type}"]`);
    }

    function profileSelect(type) {
        return document.getElementById(`${type}-select`);
    }

    function profilesOfType(type) {
        return {
            own: localProfiles.filter(profile => profile.type === type),
            library: libraryProfiles.filter(profile => profile.type === type)
        };
    }

    function renderProfileOptions(type, selectedId = '') {
        const select = profileSelect(type);
        const { own, library } = profilesOfType(type);
        select.replaceChildren(new Option(type === 'user' ? 'Create your character…' : 'Create a character…', ''));
        if (own.length) {
            const group = document.createElement('optgroup');
            group.label = 'My profiles';
            own.forEach(profile => group.appendChild(new Option(profile.name, profile.id)));
            select.appendChild(group);
        }
        if (library.length) {
            const group = document.createElement('optgroup');
            group.label = 'Approved community library';
            library.forEach(profile => group.appendChild(new Option(profile.name, profile.id)));
            select.appendChild(group);
        }
        select.value = selectedId;
        updateSubmissionButton(type);
    }

    function updateSubmissionButton(type) {
        const card = cardFor(type);
        const selected = profileSelect(type).value;
        const isOwn = localProfiles.some(profile => profile.id === selected && profile.type === type);
        card.querySelector('.submit-profile').disabled = !isOwn;
    }

    function fillForm(type, profile) {
        const card = cardFor(type);
        card.dataset.profileId = profile ? profile.id : '';
        for (const field of ['name', 'description', 'personality', 'scenario', 'first_message', 'system_instruction', 'example_dialogue']) {
            card.querySelector(`[data-field="${field}"]`).value = profile?.[field] || '';
        }
        card.querySelector('[data-field="tags"]').value = (profile?.tags || []).join(', ');
    }

    function readForm(type) {
        const card = cardFor(type);
        const profile = { type };
        const id = card.dataset.profileId;
        if (id && localProfiles.some(item => item.id === id && item.type === type)) profile.id = id;
        for (const field of ['name', 'description', 'personality', 'scenario', 'first_message', 'system_instruction', 'example_dialogue']) {
            profile[field] = card.querySelector(`[data-field="${field}"]`).value.trim();
        }
        profile.tags = card.querySelector('[data-field="tags"]').value
            .split(',').map(tag => tag.trim()).filter(Boolean);
        return profile;
    }

    async function loadData() {
        const [modelsResult, profilesResult, catalogResult] = await Promise.allSettled([
            api('/api/models'),
            api('/api/roleplay/profiles'),
            api('/api/model-catalog')
        ]);
        if (profilesResult.status === 'rejected') throw profilesResult.reason;
        const profiles = profilesResult.value;
        if (catalogResult.status === 'fulfilled') {
            modelRatings = new Map((catalogResult.value.models || []).map(model => [model.id, model]));
        }
        const models = modelsResult.status === 'fulfilled' && Array.isArray(modelsResult.value)
            ? modelsResult.value
            : [];
        if (!models.length) {
            setStatus(modelsResult.status === 'rejected'
                ? `Profiles are ready, but local models could not be loaded: ${modelsResult.reason.message}`
                : 'No local models are available. Start your local model server to begin a scene.', true);
        }
        const modelSelect = document.getElementById('roleplay-model');
        modelSelect.replaceChildren();
        models.forEach(model => modelSelect.appendChild(new Option(model, model)));
        if (!models.length) modelSelect.appendChild(new Option('No local models available', ''));
        localProfiles = profiles.profiles || [];
        libraryProfiles = profiles.library || [];
        for (const type of ['character', 'user']) renderProfileOptions(type);
        renderSessionProfileOptions('character', document.getElementById('session-character'));
        renderSessionProfileOptions('user', document.getElementById('session-user-character'));
        const sessionModel = document.getElementById('session-model');
        [...modelSelect.options].forEach(option => sessionModel.appendChild(new Option(option.textContent, option.value)));
        fillForm('character', null);
        fillForm('user', null);
        try {
            await refreshSessions();
        } catch (error) {
            setSessionStatus(`Could not load your saved scenes: ${error.message}`, true);
        }
        const requestedConversation = new URLSearchParams(location.search).get('conversation');
        if (requestedConversation) await loadSession(requestedConversation);
    }

    function renderSessionProfileOptions(type, select) {
        const selectedId = select.value;
        select.replaceChildren();
        const addGroup = (label, profiles) => {
            if (!profiles.length) return;
            const group = document.createElement('optgroup');
            group.label = label;
            profiles.forEach(profile => group.appendChild(new Option(profile.name, profile.id)));
            select.appendChild(group);
        };
        const { own, library } = profilesOfType(type);
        addGroup('My profiles', own);
        addGroup('Approved community library', library);
        if (selectedId) select.value = selectedId;
    }

    async function refreshSessions(selectedId = '') {
        const sessions = await api('/api/roleplay/conversations');
        const select = document.getElementById('resume-session');
        select.replaceChildren(new Option('Start or resume a scene…', ''));
        sessions.forEach(session => {
            select.appendChild(new Option(
                `${session.locked ? '🔒 ' : ''}${session.title}`,
                session.id
            ));
        });
        if (selectedId) select.value = selectedId;
    }

    function setSessionStatus(message, isError = false) {
        const element = document.getElementById('session-status');
        element.textContent = message;
        element.style.color = isError ? '#ff9b9b' : '';
    }

    function setRoleplayMode(enabled) {
        outOfCharacterMode = enabled;
        const toggle = document.getElementById('roleplay-mode-toggle');
        toggle.setAttribute('aria-pressed', String(enabled));
        toggle.textContent = enabled ? 'Return in character' : 'Out of character';
        document.getElementById('compose-mode-label').textContent =
            enabled ? 'Out-of-character note' : 'In character';
        document.getElementById('session-input').placeholder =
            enabled ? 'Ask a question or discuss the story…' : 'Write your next move…';
    }

    function renderSessionMessages() {
        const container = document.getElementById('session-messages');
        container.replaceChildren();
        if (!activeMessages.length) {
            const empty = document.createElement('div');
            empty.className = 'empty-scene';
            const heading = document.createElement('h2');
            heading.textContent = 'Scene ready';
            const copy = document.createElement('p');
            copy.textContent = 'Send a message to continue the story.';
            empty.append(heading, copy);
            container.appendChild(empty);
        }
        activeMessages.forEach((message, index) => {
            appendSessionMessage(
                message.role,
                message.content,
                index,
                true,
                message.speaker,
                message.roleplay_mode,
                message
            );
        });
        container.scrollTop = container.scrollHeight;
        const turns = activeMessages.filter(message => message.role === 'user').length;
        document.getElementById('scene-turn-count').textContent = `${turns} ${turns === 1 ? 'turn' : 'turns'}`;
        updateSceneTokenSummary();
        document.getElementById('regenerate-reply').disabled =
            !activeMessages.length || activeMessages[activeMessages.length - 1].role !== 'assistant';
    }

    function estimateTokens(text) {
        const value = typeof text === 'string' ? text.trim() : '';
        return value ? Math.max(1, Math.ceil(value.length / 4)) : 0;
    }

    function updateSceneTokenSummary(partial = '') {
        const total = activeMessages.reduce(
            (sum, message) => sum + estimateTokens(typeof message.content === 'string' ? message.content : ''),
            0
        ) + estimateTokens(partial);
        document.getElementById('scene-token-count').textContent = `Approx. ${total.toLocaleString()} tokens`;
    }

    function appendSessionMessage(role, content, index, includeActions = false, speaker = '', mode = '', messageData = {}) {
        const container = document.getElementById('session-messages');
        const empty = container.querySelector('.empty-scene');
        if (empty) empty.remove();
        const message = document.createElement('article');
        message.className = `message ${role === 'user' ? 'user' : 'assistant'}${mode === 'out_of_character' ? ' out-of-character' : ''}`;
        message.dataset.messageIndex = String(index);
        const label = document.createElement('div');
        label.className = 'message-label';
        label.textContent = speaker || (role === 'user'
            ? activeSession?.roleplay?.user?.name || 'You'
            : activeSession?.roleplay?.character?.name || 'Character');
        const body = document.createElement('div');
        body.className = 'message-content';
        const text = typeof content === 'string' ? content : '';
        body.innerHTML = DOMPurify.sanitize(marked.parse(text || ' '));
        const metadata = document.createElement('div');
        metadata.className = 'message-meta';
        const tokenCount = estimateTokens(text);
        const speed = Number(messageData.tokensPerSecond) || 0;
        metadata.textContent = `~${tokenCount} tokens${speed ? ` · ~${speed} tok/s` : ''}`;
        message.append(label, body, metadata);
        container.appendChild(message);
        if (includeActions && role === 'assistant') {
            const actions = document.createElement('div');
            actions.className = 'message-controls';
            const copy = document.createElement('button');
            copy.type = 'button';
            copy.className = 'secondary';
            copy.textContent = 'Copy';
            copy.addEventListener('click', async () => {
                try {
                    await navigator.clipboard.writeText(text);
                    setSessionStatus('Response copied.');
                } catch (error) {
                    setSessionStatus(`Could not copy response: ${error.message}`, true);
                }
            });
            actions.appendChild(copy);
            const modelId = messageData.model;
            if (typeof modelId === 'string' && modelId) {
                const counts = modelRatings.get(modelId) || { up: 0, down: 0 };
                const rating = document.createElement('div');
                rating.className = 'message-rating';
                for (const [vote, icon] of [['up', '👍'], ['down', '👎']]) {
                    const button = document.createElement('button');
                    button.type = 'button';
                    button.textContent = `${icon} ${counts[vote] || 0}`;
                    button.setAttribute('aria-label', vote === 'up' ? 'Rate response thumbs up' : 'Rate response thumbs down');
                    button.setAttribute('aria-pressed', String(messageData.rating === vote));
                    button.addEventListener('click', () => rateRoleplayMessage(index, vote));
                    rating.appendChild(button);
                }
                actions.appendChild(rating);
            }
            container.appendChild(actions);
        }
        return body;
    }

    async function rateRoleplayMessage(index, vote) {
        if (!activeSession) return;
        const current = activeMessages[index]?.rating === vote;
        try {
            const result = await api(
                `/api/conversations/${encodeURIComponent(activeSession.id)}/messages/${index}/rating`,
                { method: 'POST', body: JSON.stringify({ vote: current ? null : vote }) }
            );
            if (activeMessages[index]) activeMessages[index].rating = result.vote;
            const currentModel = modelRatings.get(result.model_id) || { id: result.model_id };
            modelRatings.set(result.model_id, {
                ...currentModel,
                up: result.up,
                down: result.down,
                score: result.up - result.down
            });
            renderSessionMessages();
        } catch (error) {
            setSessionStatus(`Could not save your rating: ${error.message}`, true);
        }
    }

    function updateSessionCast() {
        const roleplay = activeSession.roleplay;
        document.getElementById('session-title').textContent = activeSession.title;
        document.getElementById('session-cast').textContent =
            `${roleplay.character.name} · with ${roleplay.user.name}`;
        document.getElementById('session-character').value = roleplay.character.id;
        document.getElementById('session-user-character').value = roleplay.user.id;
        document.getElementById('session-model').value = activeSession.model || '';
        document.getElementById('scene-style').value = roleplay.scene_style || 'balanced';
        document.getElementById('scene-notes').value = roleplay.scene_notes || '';
        document.getElementById('apply-scene-changes').disabled = true;
        const recap = document.getElementById('scene-recap');
        recap.innerHTML = roleplay.recap
            ? DOMPurify.sanitize(marked.parse(roleplay.recap))
            : 'Your recap will appear here. Generate one from the conversation when you need a refresher.';
    }

    function hasPendingSceneChanges() {
        if (!activeSession) return false;
        return document.getElementById('session-character').value !== activeSession.roleplay.character.id
            || document.getElementById('session-user-character').value !== activeSession.roleplay.user.id
            || document.getElementById('session-model').value !== activeSession.model
            || document.getElementById('scene-style').value !== (activeSession.roleplay.scene_style || 'balanced')
            || document.getElementById('scene-notes').value !== (activeSession.roleplay.scene_notes || '');
    }

    async function loadSession(id) {
        try {
            let session;
            try {
                session = await api(`/api/roleplay/conversations/${encodeURIComponent(id)}`);
            } catch (error) {
                if (!error.message.toLowerCase().includes('password locked')) throw error;
                const password = prompt('This roleplay is locked. Enter its password to continue:');
                if (password === null) return;
                await api(`/api/conversations/${encodeURIComponent(id)}/unlock`, {
                    method: 'POST',
                    body: JSON.stringify({ password })
                });
                session = await api(`/api/roleplay/conversations/${encodeURIComponent(id)}`);
            }
            activeSession = session;
            activeMessages = Array.isArray(session.messages) ? session.messages : [];
            document.getElementById('setup-screen').hidden = true;
            document.getElementById('play-screen').hidden = false;
            updateSessionCast();
            setRoleplayMode(false);
            document.getElementById('send-message').disabled = false;
            renderSessionMessages();
            let sessionListError = '';
            try {
                await refreshSessions(id);
            } catch (error) {
                sessionListError = `Scene loaded, but saved scenes could not be refreshed: ${error.message}`;
            }
            history.replaceState(null, '', `/roleplay?conversation=${encodeURIComponent(id)}`);
            setSessionStatus(sessionListError, Boolean(sessionListError));
        } catch (error) {
            setSessionStatus(error.message, true);
        }
    }

    function generationParameters() {
        return {
            temperature: 0.85,
            max_tokens: 2048,
            top_p: 0.95,
            top_k: 40,
            repeat_penalty: 1.1,
            seed: -1,
            system_prompt: ''
        };
    }

    async function streamRoleplay(prompt, regenerate = false) {
        if (!activeSession || activeGenerationController) return;
        const input = document.getElementById('session-input');
        const sendButton = document.getElementById('send-message');
        const stopButton = document.getElementById('stop-generation');
        const container = document.getElementById('session-messages');
        if (!regenerate && !prompt.trim()) return;
        const requestMode = regenerate
            ? [...activeMessages].reverse().find(message => message.role === 'user')?.roleplay_mode || 'character'
            : outOfCharacterMode ? 'out_of_character' : 'character';
        const requestSpeaker = requestMode === 'out_of_character'
            ? 'Out of character'
            : activeSession.roleplay.user.name;

        if (regenerate) {
            activeMessages.pop();
            container.lastElementChild?.remove();
            container.lastElementChild?.remove();
        } else {
            const userMessage = {
                role: 'user',
                content: prompt.trim(),
                speaker: requestSpeaker,
                ...(requestMode === 'out_of_character' ? { roleplay_mode: requestMode } : {})
            };
            activeMessages.push(userMessage);
            appendSessionMessage(
                'user',
                userMessage.content,
                activeMessages.length - 1,
                false,
                userMessage.speaker,
                requestMode
            );
            input.value = '';
            const turns = activeMessages.filter(message => message.role === 'user').length;
            document.getElementById('scene-turn-count').textContent = `${turns} ${turns === 1 ? 'turn' : 'turns'}`;
        }
        const assistantBody = appendSessionMessage(
            'assistant',
            '',
            activeMessages.length,
            false,
            requestMode === 'out_of_character' ? 'Out of character' : activeSession.roleplay.character.name,
            requestMode
        );
        const assistantArticle = assistantBody.closest('.message');
        const controller = new AbortController();
        const generationId = crypto.randomUUID().replace(/-/g, '');
        activeGenerationController = controller;
        activeGenerationId = generationId;
        sendButton.disabled = true;
        document.getElementById('regenerate-reply').disabled = true;
        stopButton.hidden = false;
        document.getElementById('resume-session').disabled = true;
        document.getElementById('edit-scene').disabled = true;
        document.getElementById('apply-scene-changes').disabled = true;
        document.getElementById('roleplay-mode-toggle').disabled = true;
        document.getElementById('create-recap').disabled = true;
        setSessionStatus('Generating…');
        container.scrollTop = container.scrollHeight;

        let responseText = '';
        const generationStartedAt = performance.now();
        const messageMetadata = assistantArticle.querySelector('.message-meta');
        const modelId = document.getElementById('session-model').value;
        try {
            const response = await fetch('/api/chat/stream', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRF-Token': csrfToken
                },
                body: JSON.stringify({
                    conversation_id: activeSession.id,
                    prompt: regenerate ? undefined : prompt.trim(),
                    regenerate,
                    model: modelId,
                    params: generationParameters(),
                    roleplay_mode: requestMode,
                    generation_id: generationId
                }),
                signal: controller.signal
            });
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || `HTTP ${response.status}`);
            }
            if (!response.body) throw new Error('This browser does not support streamed responses.');
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            let completed = false;
            const processFrame = frame => {
                const line = frame.split('\n').find(item => item.startsWith('data:'));
                if (!line) return;
                const event = JSON.parse(line.slice(5).trim());
                if (event.error) throw new Error(event.error);
                if (event.content) {
                    responseText += event.content;
                    assistantBody.innerHTML = DOMPurify.sanitize(marked.parse(responseText || ' '));
                    const tokens = estimateTokens(responseText);
                    const elapsed = Math.max(0.1, (performance.now() - generationStartedAt) / 1000);
                    messageMetadata.textContent = `~${tokens} tokens · ~${Math.round(tokens / elapsed)} tok/s`;
                    updateSceneTokenSummary(responseText);
                    container.scrollTop = container.scrollHeight;
                }
                if (event.done) completed = true;
            };
            while (!completed) {
                const { value, done } = await reader.read();
                buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
                const frames = buffer.split(/\r?\n\r?\n/);
                buffer = frames.pop() || '';
                frames.forEach(processFrame);
                if (done) break;
            }
            if (responseText) {
                activeMessages.push({
                    role: 'assistant',
                    content: responseText,
                    speaker: requestMode === 'out_of_character'
                        ? 'Out of character'
                        : activeSession.roleplay.character.name,
                    model: modelId,
                    tokensPerSecond: Math.round(
                        estimateTokens(responseText) / Math.max(0.1, (performance.now() - generationStartedAt) / 1000)
                    ),
                    ...(requestMode === 'out_of_character' ? { roleplay_mode: requestMode } : {})
                });
                renderSessionMessages();
            }
            try {
                await refreshSessions(activeSession.id);
                setSessionStatus('');
            } catch (error) {
                setSessionStatus(`Reply saved, but saved scenes could not be refreshed: ${error.message}`, true);
            }
        } catch (error) {
            if (!controller.signal.aborted) {
                await loadSession(activeSession.id);
                setSessionStatus(error.message, true);
            }
        } finally {
            activeGenerationController = null;
            activeGenerationId = null;
            sendButton.disabled = hasPendingSceneChanges();
            stopButton.hidden = true;
            document.getElementById('resume-session').disabled = false;
            document.getElementById('edit-scene').disabled = false;
            document.getElementById('apply-scene-changes').disabled = false;
            document.getElementById('roleplay-mode-toggle').disabled = false;
            document.getElementById('create-recap').disabled = false;
            document.getElementById('regenerate-reply').disabled =
                hasPendingSceneChanges()
                || !activeMessages.length
                || activeMessages[activeMessages.length - 1].role !== 'assistant';
        }
    }

    for (const type of ['character', 'user']) {
        profileSelect(type).addEventListener('change', () => {
            const profile = [...localProfiles, ...libraryProfiles].find(item => item.id === profileSelect(type).value);
            fillForm(type, profile || null);
            updateSubmissionButton(type);
        });

        cardFor(type).querySelector('.save-profile').addEventListener('click', async event => {
            const button = event.currentTarget;
            button.disabled = true;
            try {
                const profile = await api('/api/roleplay/profiles', {
                    method: 'POST',
                    body: JSON.stringify(readForm(type))
                });
                localProfiles = localProfiles.filter(item => item.id !== profile.id);
                localProfiles.push(profile);
                renderProfileOptions(type, profile.id);
                renderSessionProfileOptions('character', document.getElementById('session-character'));
                renderSessionProfileOptions('user', document.getElementById('session-user-character'));
                fillForm(type, profile);
                setStatus(`${profile.name} saved to your private profiles.`);
            } catch (error) {
                setStatus(error.message, true);
            } finally {
                button.disabled = false;
            }
        });

        cardFor(type).querySelector('.submit-profile').addEventListener('click', async () => {
            const profileId = profileSelect(type).value;
            try {
                await api(`/api/roleplay/profiles/${encodeURIComponent(profileId)}/submit`, { method: 'POST' });
                setStatus('Profile submitted for moderator review.');
            } catch (error) {
                setStatus(error.message, true);
            }
        });

        cardFor(type).querySelector('.generate-profile').addEventListener('click', async event => {
            const button = event.currentTarget;
            const idea = document.getElementById(`${type}-idea`).value.trim();
            const model = document.getElementById('roleplay-model').value;
            if (!model) {
                setStatus('Start your local model server and choose a model first.', true);
                return;
            }
            button.disabled = true;
            button.textContent = 'Generating…';
            try {
                const profile = await api('/api/roleplay/generate-profile', {
                    method: 'POST',
                    body: JSON.stringify({ type, idea, model })
                });
                fillForm(type, profile);
                profileSelect(type).value = '';
                setStatus(`Draft generated for ${profile.name}. Review it, then save.`);
            } catch (error) {
                setStatus(error.message, true);
            } finally {
                button.disabled = false;
                button.textContent = 'Generate';
            }
        });
    }

    document.getElementById('start-roleplay').addEventListener('click', async event => {
        const button = event.currentTarget;
        const characterId = document.getElementById('character-select').value;
        const userId = document.getElementById('user-select').value;
        const model = document.getElementById('roleplay-model').value;
        if (!characterId || !userId || !model) {
            setStatus('Choose a character, your character, and a local model. Save new drafts first.', true);
            return;
        }
        button.disabled = true;
        try {
            const result = await api('/api/roleplay/conversations', {
                method: 'POST',
                body: JSON.stringify({
                    character_id: characterId,
                    user_id: userId,
                    model,
                    title: document.getElementById('roleplay-title').value.trim() || undefined,
                    password: document.getElementById('roleplay-password').value || undefined
                })
            });
            await loadSession(result.id);
        } catch (error) {
            setStatus(error.message, true);
            button.disabled = false;
        }
    });

    document.getElementById('session-form').addEventListener('submit', event => {
        event.preventDefault();
        streamRoleplay(document.getElementById('session-input').value);
    });

    document.getElementById('session-input').addEventListener('keydown', event => {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            document.getElementById('session-form').requestSubmit();
        }
    });

    document.getElementById('stop-generation').addEventListener('click', async () => {
        if (!activeGenerationId) return;
        try {
            await api('/api/chat/cancel', {
                method: 'POST',
                body: JSON.stringify({ generation_id: activeGenerationId })
            });
            setSessionStatus('Stopping generation…');
        } catch (error) {
            setSessionStatus(error.message, true);
        }
    });

    document.getElementById('regenerate-reply').addEventListener('click', () => {
        if (activeMessages.length && activeMessages[activeMessages.length - 1].role === 'assistant') {
            streamRoleplay('', true);
        }
    });

    document.getElementById('apply-scene-changes').addEventListener('click', async event => {
        const button = event.currentTarget;
        button.disabled = true;
        try {
            const updated = await api(`/api/roleplay/conversations/${encodeURIComponent(activeSession.id)}`, {
                method: 'PUT',
                body: JSON.stringify({
                    character_id: document.getElementById('session-character').value,
                    user_id: document.getElementById('session-user-character').value,
                    model: document.getElementById('session-model').value,
                    scene_style: document.getElementById('scene-style').value,
                    scene_notes: document.getElementById('scene-notes').value
                })
            });
            activeSession.roleplay = updated.roleplay;
            activeSession.model = updated.model;
            updateSessionCast();
            document.getElementById('send-message').disabled = false;
            renderSessionMessages();
            setSessionStatus('Scene changes applied. Your history is unchanged.');
        } catch (error) {
            setSessionStatus(error.message, true);
        } finally {
            button.disabled = !hasPendingSceneChanges();
        }
    });

    ['session-character', 'session-user-character', 'session-model', 'scene-style', 'scene-notes'].forEach(id => {
        document.getElementById(id).addEventListener('change', () => {
            const pending = hasPendingSceneChanges();
            document.getElementById('apply-scene-changes').disabled = !pending;
            document.getElementById('send-message').disabled = pending;
            document.getElementById('regenerate-reply').disabled = pending
                || !activeMessages.length
                || activeMessages[activeMessages.length - 1].role !== 'assistant';
            setSessionStatus(pending ? 'Apply your scene changes before sending the next message.' : '');
        });
    });
    document.getElementById('scene-notes').addEventListener('input', () => {
        const pending = hasPendingSceneChanges();
        document.getElementById('apply-scene-changes').disabled = !pending;
        document.getElementById('send-message').disabled = pending;
    });

    document.getElementById('roleplay-mode-toggle').addEventListener('click', () => {
        setRoleplayMode(!outOfCharacterMode);
    });

    document.getElementById('create-recap').addEventListener('click', async event => {
        if (hasPendingSceneChanges()) {
            setSessionStatus('Save your scene setup before creating a recap.', true);
            return;
        }
        const button = event.currentTarget;
        button.disabled = true;
        button.textContent = 'Creating…';
        setSessionStatus('Creating a continuity recap with the selected local model…');
        try {
            const result = await api(
                `/api/roleplay/conversations/${encodeURIComponent(activeSession.id)}/recap`,
                { method: 'POST', body: JSON.stringify({}) }
            );
            activeSession.roleplay.recap = result.recap;
            document.getElementById('scene-recap').innerHTML =
                DOMPurify.sanitize(marked.parse(result.recap));
            setSessionStatus('Recap saved with this scene.');
        } catch (error) {
            setSessionStatus(error.message, true);
        } finally {
            button.disabled = false;
            button.textContent = 'Create recap';
        }
    });

    document.getElementById('edit-scene').addEventListener('click', () => {
        document.getElementById('play-screen').hidden = true;
        document.getElementById('setup-screen').hidden = false;
        history.replaceState(null, '', '/roleplay');
    });

    document.getElementById('resume-session').addEventListener('change', event => {
        if (event.currentTarget.value) loadSession(event.currentTarget.value);
    });

    if (window.matchMedia('(max-width: 760px)').matches) {
        document.getElementById('scene-dashboard').open = false;
    }

    loadData().catch(error => setStatus(error.message, true));
})();