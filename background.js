// noinspection ES6MissingAwait

const state = self.serviceWorker.state

importScripts('libs/idb.umd.js')
importScripts('projects.js')
importScripts('main.js')

// TODO Delayed importScripts don't work yet, more details https://bugs.chromium.org/p/chromium/issues/detail?id=1198822
self.addEventListener('install', () => {
    importScripts('libs/linkedom.js')
    importScripts('scripts/mcserver-list.eu_silentvote.js', 'scripts/misterlauncher.org_silentvote.js', 'scripts/serverpact.com_silentvote.js', 'scripts/genshindrop.com_silentvote.js')
})

//Current fetch requests
// noinspection ES6ConvertVarToLetConst
// var fetchProjects = new Map()
//Tab group ID where extension tabs are currently open
let groupId
//If this browser doesn't support tab grouping
let notSupportedGroupTabs = false

//Whether to check voting now, false can only be when the previous check is not yet completed
let check = true
let doubleCheck = false

let silentResponseBody = {}

//Initialize extension settings
// noinspection JSIgnoredPromiseFromCall
const initializeFunc = initializeConfig(true)
initializeFunc.finally(() => initializeFunc.done = true)

//Check: whether to vote, compares current time with time from config
async function checkVote() {

    await initializeFunc

    // noinspection JSUnresolvedReference
    if (!settings.operaAttention2 && (navigator?.userAgentData?.brands?.[0]?.brand === 'Opera' || (!!self.opr && !!opr.addons) || !!self.opera || navigator.userAgent.indexOf(' OPR/') >= 0)) {
        return
    }

    //If there was no internet after voting attempt, check if there is internet now and if not, prevent subsequent checks. But if internet appeared, set online status to true and continue
    if (!settings.disabledCheckInternet && !onLine) {
        if (navigator.onLine) {
            console.log(chrome.i18n.getMessage('internetRestored'))
            onLine = true
            db.put('other', onLine, 'onLine')
        } else {
            // TODO Unfortunately, Service Worker doesn't have a listener for restoring internet connection, we only have 1 option - try to restart checkVote in a minute
            chrome.alarms.create('checkVote', {when: Date.now() + 65000})
            return
        }
    }

    if (check) {
        check = false
    } else {
        doubleCheck = true
        return
    }

    const transaction = db.transaction('projects')
    let cursor = await transaction.objectStore('projects').openCursor()
    while (cursor) {
        const project = cursor.value
        if (!project.time || project.time < Date.now()) {
            await checkOpen(project, transaction)
        }
        // noinspection JSVoidFunctionReturnValueUsed
        cursor = await cursor.continue()
    }

    check = true
    if (doubleCheck) {
        doubleCheck = false
        checkVote()
    } else {
        // Voting completed and no more planned
        if (!openedProjects.size) {
            promises = []
            updateListeners(false)
        }
    }
}

//Trigger for voting when voting time comes
chrome.alarms.onAlarm.addListener(function (alarm) {
    if (settings?.debug) console.log('chrome.alarms.onAlarm', JSON.stringify(alarm))
    // noinspection JSIgnoredPromiseFromCall
    checkVote()
})

// TODO Workaround for the bug https://bugs.chromium.org/p/chromium/issues/detail?id=471524
chrome.idle.onStateChanged.addListener(async function(newState) {
    if (newState === 'active') {
        // noinspection JSIgnoredPromiseFromCall
        checkVote()
    }
})

async function reloadAllAlarms() {
    await chrome.alarms.clearAll()
    let cursor = await db.transaction('projects').store.openCursor()
    const times = []
    while (cursor) {
        const project = cursor.value
        if (project.time != null && project.time > Date.now() && times.indexOf(project.time) === -1) {
            let when = project.time
            if (when - Date.now() < 65000) when = Date.now() + 65000
            try {
                chrome.alarms.create(String(cursor.key), {when})
            } catch (error) {
                console.warn(getProjectPrefix(project, true), 'Ошибка при создании chrome.alarms', error.message)
            }
            times.push(project.time)
        }
        // noinspection JSVoidFunctionReturnValueUsed
        cursor = await cursor.continue()
    }
}

let promises = []
async function checkOpen(project, transaction) {
    //If no internet, don't vote
    if (!settings.disabledCheckInternet) {
        if (!navigator.onLine && onLine) {
            // TODO Unfortunately, Service Worker doesn't have a listener for restoring internet connection, we only have 1 option - try to restart checkVote in a minute
            chrome.alarms.create('checkVote', {when: Date.now() + 65000})

            sendNotification(getProjectPrefix(project, false), chrome.i18n.getMessage('internetDisconnected'), 'error', 'openProject_' + project.key)
            console.warn(getProjectPrefix(project, true), chrome.i18n.getMessage('internetDisconnected'))
            onLine = false
            db.put('other', onLine, 'onLine')
            return
        } else if (!onLine) {
            return
        }
    }

    for (let[tab,value] of openedProjects) {
        if (value.timeoutQueue && Date.now() >= value.timeoutQueue) {
            openedProjects.delete(tab)
            db.put('other', openedProjects, 'openedProjects')
            continue
        }
        if (project.rating === value.rating || (value.randomize && project.randomize) || settings.disabledOneVote) {
            if (settings.disabledRestartOnTimeout || tab.startsWith?.('queue_') || Date.now() < value.nextAttempt) {
                return
            } else {
                openedProjects.delete(tab)
                db.put('other', openedProjects, 'openedProjects')

                const projectTimeout = await transaction.objectStore('projects').get(value.key)
                if (!value.nextAttempt) {
                    console.warn(getProjectPrefix(projectTimeout, true), 'nextAttempt is undefined, maybe it\'s an error')
                }
                console.warn(getProjectPrefix(projectTimeout, true), chrome.i18n.getMessage('timeout'))
                sendNotification(getProjectPrefix(projectTimeout, false), chrome.i18n.getMessage('timeout'), 'warn', 'openProject_' + project.key)

                // noinspection JSIgnoredPromiseFromCall
                if (!settings.disableCloseTabsOnError) tryCloseTab(tab, projectTimeout, 0)
                break
            }
        }
    }

    delete project.timeoutQueue
    delete project.nextAttempt
    delete project.countInject

    const opened = {}
    opened.key = project.key
    opened.rating = project.rating
    opened.countInject = 0
    if (project.randomize) opened.randomize = project.randomize

    if (!settings.disabledRestartOnTimeout) {
        let retryCoolDown
        if (project.randomize) {
            retryCoolDown = Math.floor(Math.random() * 600000 + 1800000)
        } else {
            if (!settings.timeoutVote) settings.timeoutVote = 900000
            retryCoolDown = settings.timeoutVote
        }
        opened.nextAttempt = Date.now() + retryCoolDown
    }

    // Voting starts for the first time
    if (!openedProjects.size) {
        updateListeners(true)
    }

    openedProjects.set('start_' + project.key, opened)
    db.put('other', openedProjects, 'openedProjects')

    if (settings.debug) console.log(getProjectPrefix(project, true), 'пред запуск')

    if (project.rating === 'monitoringminecraft.ru') {
        promises.push(clearMonitoringMinecraftCookies())
        async function clearMonitoringMinecraftCookies() {
            let url
            if (project.rating === 'monitoringminecraft.ru') {
                url = '.monitoringminecraft.ru'
            }
            let cookies = await chrome.cookies.getAll({domain: url})
            if (settings.debug) console.log(chrome.i18n.getMessage('deletingCookies', url))
            for (let i = 0; i < cookies.length; i++) {
                if (cookies[i].domain.charAt(0) === '.') cookies[i].domain = cookies[i].domain.substring(1, cookies[i].domain.length)
                await chrome.cookies.remove({url: 'https://' + cookies[i].domain + cookies[i].path, name: cookies[i].name})
            }
        }
    }

    // noinspection JSIgnoredPromiseFromCall
    newWindow(project, opened)
}

let promiseGroup
let promiseWindow
//Opens a tab for voting or starts executing fetch requests
async function newWindow(project, opened) {
    //Wait for cookie cleanup
    let result = await Promise.all(promises)
    while (result.length < promises.length) {
        result = await Promise.all(promises)
    }

    console.log(getProjectPrefix(project, true), chrome.i18n.getMessage('startedAutoVote'))
    sendNotification(getProjectPrefix(project, false), chrome.i18n.getMessage('startedAutoVote'), 'start', 'openProject_' + project.key)

    if (new Date(project.stats.lastAttemptVote).getMonth() < new Date().getMonth() || new Date(project.stats.lastAttemptVote).getFullYear() < new Date().getFullYear()) {
        project.stats.lastMonthSuccessVotes = project.stats.monthSuccessVotes
        project.stats.monthSuccessVotes = 0
    }
    project.stats.lastAttemptVote = Date.now()

    if (new Date(generalStats.lastAttemptVote).getMonth() < new Date().getMonth() || new Date(generalStats.lastAttemptVote).getFullYear() < new Date().getFullYear()) {
        generalStats.lastMonthSuccessVotes = generalStats.monthSuccessVotes
        generalStats.monthSuccessVotes = 0
    }
    generalStats.lastAttemptVote = Date.now()

    if (new Date(todayStats.lastAttemptVote).getDay() < new Date().getDay()) {
        todayStats = {
            successVotes: 0,
            errorVotes: 0,
            laterVotes: 0,
            lastSuccessVote: null,
            lastAttemptVote: null
        }
    }
    todayStats.lastAttemptVote = Date.now()
    await db.put('other', generalStats, 'generalStats')
    await db.put('other', todayStats, 'todayStats')
    await updateValue('projects', project)

    if (!settings.disabledRestartOnTimeout) {
        let create = true
        let alarms = await chrome.alarms.getAll()
        for (const alarm of alarms) {
            if (alarm.scheduledTime === opened.nextAttempt) {
                create = false
                break
            }
        }
        if (create) {
            let when = opened.nextAttempt
            if (when - Date.now() < 65000) when = Date.now() + 65000
            try {
                await chrome.alarms.create('nextAttempt_' + project.key, {when})
            } catch (error) {
                console.warn(getProjectPrefix(project, true), 'Ошибка при создании chrome.alarms', error.message)
            }
        }
    }

    let silentVoteMode = false
    if (project.rating === 'Custom') {
        silentVoteMode = true
    } else if (!project.emulateMode && allProjects[project.rating].silentVote?.(project)) {
        silentVoteMode = true
    }
    if (silentVoteMode) {
        openedProjects.set('background_' + project.key, opened)
        openedProjects.delete('start_' + project.key)
        db.put('other', openedProjects, 'openedProjects')
        silentVote(project)
    } else {
        let result = await promiseWindow
        if (result === false) return
        promiseWindow = checkWindow(project)
        result = await promiseWindow
        if (result === false) return

        const url = allProjects[project.rating].voteURL(project)

        let tab = await tryOpenTab({url, active: settings.disabledFocusedTab || Boolean(allProjects[project.rating].focusedTab?.(project))}, project, 0)
        if (tab == null) return
        openedProjects.set(tab.id, opened)
        openedProjects.delete('start_' + project.key)
        db.put('other', openedProjects, 'openedProjects')

        if (notSupportedGroupTabs) return
        try {
            await promiseGroup
            promiseGroup = groupTabs(tab)
            await promiseGroup
        } catch (error) {
            if (error.message === 'Tabs cannot be edited right now (user may be dragging a tab).') {
                console.warn(getProjectPrefix(project, true), 'Error when grouping tabs,', error.message)
            } else {
                notSupportedGroupTabs = true
                console.warn(chrome.i18n.getMessage('notSupportedGroupTabs'), error.message)
            }
        }
    }
}

async function checkWindow(project) {
    const windows = await chrome.windows.getAll()
        .catch(error => console.warn(chrome.i18n.getMessage('errorOpenTab', error.message)))
    if (!windows?.length) {
        try {
            const window = await chrome.windows.create({focused: false})
            await chrome.windows.update(window.id, {focused: false, drawAttention: false})
        } catch (error) {
            endVote({errorOpenTab: error.message}, null, project)
            return false
        }
    }
    return true
}

async function groupTabs(tab) {
    // First, look for tab group
    if (groupId == null) {
        const groups = await chrome.tabGroups.query({title: 'Auto Vote Rating'})
        if (groups.length) groupId = groups[0].id
    }

    // Then try to group if we found a group
    if (groupId != null) {
        try {
            await tryGroupTabs({groupId, tabIds: tab.id}, 0)
            return
        } catch (error) {
            if (!error.message.includes('No tab with id') && !error.message.includes('No group with id')) {
                throw error
            }
        }
    }

    // If we didn't find groups or couldn't group because there's no such group anymore, only then create this group
    try {
        groupId = await tryGroupTabs({tabIds: tab.id}, 0)
        await chrome.tabGroups.update(groupId, {color: 'blue', title: 'Auto Vote Rating'})
    } catch (error) {
        if (!error.message.includes('No tab with id') && !error.message.includes('No group with id')) {
            throw error
        }
    }
}

async function silentVote(project) {
    if (!self.DOMParser) {
        importScripts('libs/linkedom.js')
    }
    try {
        if (project.rating === 'Custom') {
            let response = await fetch(project.responseURL, {...project.body})
            await response.text()
            if (response.ok) {
                endVote({successfully: true}, null, project)
            } else {
                endVote({errorVote: [String(response.status), response.url]}, null, project)
            }
            return
        }

        if (!self['silentVote' + project.rating]) {
            importScripts('scripts/' + (project.ratingMain || project.rating) + '_silentvote.js')
        }

        await self['silentVote_' + (project.ratingMain || project.rating)](project)
    } catch (error) {
        if (error.message.includes('Failed to fetch') || error.message.includes('NetworkError when attempting to fetch resource')) {
            // let found = false
            // for (const p of fetchProjects.values()) {
            //     if (p.key === project.key) {
            //         found = true
            //         break
            //     }
            // }
            // if (!found) {
                endVote({notConnectInternet: true}, null, project)
                // endVote({message: chrome.i18n.getMessage('errorVoteUnknown') + (error.stack ? error.stack : e)}, null, project)
            // }
        } else {
            let message
            if (error.stack) {
                message = error.stack
            } else {
                message = error.message
            }
            const request = {}
            request.errorVoteNoElement = message
            if (silentResponseBody[project.rating]) {
                request.html = silentResponseBody[project.rating].doc.body.outerHTML
                request.url = silentResponseBody[project.rating].url
            }
            endVote(request, null, project)
        }
    } finally {
        delete silentResponseBody[project.rating]
    }
}

async function checkResponseError(project, response, url, bypassCodes, vk) {
    let host = extractHostname(response.url)
    if (vk && host.includes('vk.com')) {
        if (response.headers.get('Content-Type') && response.headers.get('Content-Type').includes('windows-1251')) {
            //Why not UTF-8?
            response = await new Response(new TextDecoder('windows-1251').decode(await response.arrayBuffer()))
        }
    }
    response.html = await response.text()
    response.doc = new DOMParser().parseFromString(response.html, 'text/html')
    silentResponseBody[project.rating] = {}
    silentResponseBody[project.rating].doc = response.doc
    silentResponseBody[project.rating].url = response.url
    if (vk && host.includes('vk.com')) {
        //Find out the reason why we're stuck on VK authorization
        let text
        if (response.doc.querySelector('div.oauth_form_access') != null) {
            text = response.doc.querySelector('div.oauth_form_access').textContent.replace(response.doc.querySelector('div.oauth_access_items').textContent, '').trim()
        } else if (response.doc.querySelector('div.oauth_content > div') != null) {
            text = response.doc.querySelector('div.oauth_content > div').textContent
        } else if (response.doc.querySelector('#login_blocked_wrap') != null) {
            text = response.doc.querySelector('#login_blocked_wrap div.header').textContent + ' ' + response.doc.querySelector('#login_blocked_wrap div.content').textContent.trim()
        } else if (response.doc.querySelector('div.login_blocked_panel') != null) {
            text = response.doc.querySelector('div.login_blocked_panel').textContent.trim()
        } else if (response.doc.querySelector('.profile_deleted_text') != null) {
            text = response.doc.querySelector('.profile_deleted_text').textContent.trim()
        } else if (response.html.length < 500) {
            text = response.html
        } else {
            text = 'null'
        }
        endVote({errorAuthVK: text}, null, project)
        return false
    }
    if (!host.includes(url)) {
        endVote({message: chrome.i18n.getMessage('errorRedirected', response.url)}, null, project)
        return false
    }
    if (bypassCodes) {
        for (const code of bypassCodes) {
            if (response.status === code) {
                return true
            }
        }
    }
    if (!response.ok) {
        endVote({errorVote: [String(response.status), response.url]}, null, project)
        return false
    }
    if (response.statusText && response.statusText !== '' && response.statusText !== 'ok' && response.statusText !== 'OK') {
        endVote(response.statusText, null, project)
        return false
    }
    return true
}

const webNavigationOnCommittedListener = function(details) {
    if (!initializeFunc.done) {
        (async () => {
            await initializeFunc
            let opened = openedProjects.get(details.tabId)
            if (!opened) return
            const project = await db.get('projects', opened.key)
            let message = chrome.i18n.getMessage('notReadyInject')
            if (project.error === message) return
            console.warn(getProjectPrefix(project, true), message)
            sendNotification(getProjectPrefix(project, false), message, 'warn', 'openProject_' + project.key)
            project.error = message
            updateValue('projects', project)
        })()
        return
    }

    let opened = openedProjects.get(details.tabId)
    if (!opened) return
    if (details.url.startsWith('blob:')) return
    const filesIsolated = []
    const filesMain = []
    if (details.frameId === 0) {
        // User can authorize through these sites, I don't support automatic authorization yet, don't interfere with their authorization
        if (details.url.match(/facebook.com\/*/) || details.url.match(/google.com\/*/) || details.url.match(/accounts.google.com\/*/) || details.url.match(/reddit.com\/*/) || details.url.match(/twitter.com\/*/)) {
            return
        }
        // If user authorizes through these sites but the extension doesn't have permissions, still don't interfere, let them authorize manually despite automation being available
        // if (details.url.match(/vk.com\/*/) || details.url.match(/discord.com\/*/) || details.url.startsWith('https://steamcommunity.com/openid/login') || details.url.startsWith('https://steamcommunity.com/login/home')) {
        //     // noinspection JSUnresolvedFunction
        //     let granted = await chrome.permissions.contains({origins: [details.url]})
        //     if (!granted) {
        //         return
        //     }
        // }

        filesMain.push('scripts/main/visible.js')
        if (allProjects[getDomainWithoutSubdomain(details.url)]?.needIsTrusted?.()) {
            filesIsolated.push('scripts/main/istrusted_isolated.js')
            filesMain.push('scripts/main/istrusted_main.js')
        }
        if (!allProjects[getDomainWithoutSubdomain(details.url)]?.dontUseAlert?.()) {
            filesIsolated.push('scripts/main/alert_isolated.js')
            filesMain.push('scripts/main/alert_main.js')
        }
    } else if (details.url.match(/hcaptcha.com\/captcha\/*/)
            || details.url.match(/https?:\/\/(.+?\.)?google.com\/recaptcha\/api.\/anchor*/)
            || details.url.match(/https?:\/\/(.+?\.)?google.com\/recaptcha\/api.\/bframe*/)
            || details.url.match(/https?:\/\/(.+?\.)?recaptcha.net\/recaptcha\/api.\/anchor*/)
            || details.url.match(/https?:\/\/(.+?\.)?recaptcha.net\/recaptcha\/api.\/bframe*/)
            || details.url.match(/https?:\/\/(.+?\.)?google.com\/recaptcha\/api\/fallback*/)
            || details.url.match(/https?:\/\/(.+?\.)?recaptcha.net\/recaptcha\/api\/fallback*/)
            || details.url.match(/https?:\/\/(.+?\.)?recaptcha.net\/recaptcha\/enterprise\/fallback*/)
            || details.url.match(/https?:\/\/(.+?\.)?google.com\/recaptcha\/enterprise\/anchor*/)
            || details.url.match(/https?:\/\/(.+?\.)?recaptcha.net\/recaptcha\/enterprise\/bframe*/)
            || details.url.match(/https:\/\/challenges.cloudflare.com\/*/)) {
        filesMain.push('scripts/main/visible.js')
        filesIsolated.push('scripts/main/alert_isolated.js')
        filesMain.push('scripts/main/alert_main.js')
    }

    if (!filesIsolated.length && !filesMain.length) return

    if (settings.debug) console.log('Injecting ' + JSON.stringify(filesIsolated) + ', ' + JSON.stringify(filesMain) + ' to ' + details.url)

    let target = {tabId: details.tabId}
    if (details.frameId) target.frameIds = [details.frameId]

    if (filesIsolated.length) {
        chrome.scripting.executeScript({target, files: filesIsolated, injectImmediately: true}, () => {
            const error = chrome.runtime.lastError
            if (error) {
                catchTabError(error, opened)
            }
        })
    }
    if (filesMain.length) {
        chrome.scripting.executeScript({target, files: filesMain, world: 'MAIN', injectImmediately: true}, () => {
            const error = chrome.runtime.lastError
            if (error) {
                catchTabError(error, opened)
            }
        })
    }
}

//Listener for tab updates, if tab is fully loaded, injects the script that clicks the vote button
const webNavigationOnCompletedListener = async function(details) {
    await initializeFunc
    let opened = openedProjects.get(details.tabId)
    if (!opened) return

    if (details.frameId === 0) {
        // User can authorize through these sites, I don't support automatic authorization yet, don't interfere with their authorization
        if (details.url.match(/facebook.com\/*/) || details.url.match(/google.com\/*/) || details.url.match(/accounts.google.com\/*/) || details.url.match(/reddit.com\/*/) || details.url.match(/twitter.com\/*/)) {
            return
        }

        const project = await db.get('projects', opened.key)

        // If user authorizes through these sites but the extension doesn't have permissions, still don't interfere, let them authorize manually despite automation being available
        // if (details.url.match(/vk.com\/*/) || details.url.match(/discord.com\/*/) || details.url.startsWith('https://steamcommunity.com/openid/login') || details.url.startsWith('https://steamcommunity.com/login/home')) {
        //     // noinspection JSUnresolvedFunction
        //     let granted = await chrome.permissions.contains({origins: [details.url]})
        //     if (!granted) {
        //         console.warn(getProjectPrefix(project, true), 'Not granted permissions for ' + details.url)
        //         return
        //     }
        // }

        if (opened.countInject >= 10) {
            endVote({tooManyVoteAttempts: true}, {tab: {id: details.tabId}, url: details.url}, opened)
            return
        }

        try {
            if (allProjects[project.rating]?.needPrompt?.()) {
                const funcPrompt = function(nick) {
                    // noinspection JSUnusedLocalSymbols
                    window.prompt = new Proxy(window.prompt, {
                        apply(target, thisArg, argArray) {
                            return nick
                        }
                    })
                }
                if (settings.debug) console.log('Injecting funcPrompt to ' + details.url)
                await chrome.scripting.executeScript({target: {tabId: details.tabId}, world: 'MAIN', func: funcPrompt, args: [project.nick]})
            }

            if (settings.debug) console.log('Injecting scripts/' + project.rating.toLowerCase() +'.js, scripts/main/api.js to ' + details.url)
            await chrome.scripting.executeScript({target: {tabId: details.tabId}, files: ['scripts/main/hacktimer.js', 'scripts/' + (project.ratingMain || project.rating) +'.js', 'scripts/main/api.js']})
            // noinspection JSUnresolvedVariable,JSUnresolvedFunction
            if (allProjects[project.rating]?.needWorld?.()) {
                if (settings.debug) console.log('Injecting scripts/' + project.rating.toLowerCase() +'_world.js to ' + details.url + ' in MAIN world')
                await chrome.scripting.executeScript({target: {tabId: details.tabId}, world: 'MAIN', files: ['scripts/' + (project.ratingMain || project.rating) +'_world.js']})
            }

            await chrome.tabs.sendMessage(details.tabId, {sendProject: true, project, settings})

            if (openedProjects.has(details.tabId)) {
                opened.countInject++
                db.put('other', openedProjects, 'openedProjects')
            }
        } catch (error) {
            catchTabError(error, project)
        }
    } else if (details.frameId !== 0 && (
        details.url.match(/hcaptcha.com\/captcha\/*/)
        || details.url.match(/https?:\/\/(.+?\.)?google.com\/recaptcha\/api.\/anchor*/)
        || details.url.match(/https?:\/\/(.+?\.)?google.com\/recaptcha\/api.\/bframe*/)
        || details.url.match(/https?:\/\/(.+?\.)?recaptcha.net\/recaptcha\/api.\/anchor*/)
        || details.url.match(/https?:\/\/(.+?\.)?recaptcha.net\/recaptcha\/api.\/bframe*/)
        || details.url.match(/https?:\/\/(.+?\.)?google.com\/recaptcha\/api\/fallback*/)
        || details.url.match(/https?:\/\/(.+?\.)?recaptcha.net\/recaptcha\/api\/fallback*/)
        || details.url.match(/https?:\/\/(.+?\.)?recaptcha.net\/recaptcha\/enterprise\/fallback*/)
        || details.url.match(/https?:\/\/(.+?\.)?google.com\/recaptcha\/enterprise\/anchor*/)
        || details.url.match(/https?:\/\/(.+?\.)?recaptcha.net\/recaptcha\/enterprise\/bframe*/)
        || details.url.match(/https:\/\/challenges.cloudflare.com\/*/))) {

        const project = await db.get('projects', opened.key)

        try {
            if (settings.debug) console.log('Injecting scripts/main/captchaclicker.js to ' + details.url)
            await chrome.scripting.executeScript({target: {tabId: details.tabId, frameIds: [details.frameId]}, files: ['scripts/main/hacktimer.js', 'scripts/main/captchaclicker.js']})

            // If tab is already loaded, send sendProject again which indicates we're ready to vote
            const tab = await chrome.tabs.get(details.tabId)
            // TODO Workaround for Kiwi Browser compatibility, this browser returns undefined in tab.status, we have no choice but to ignore this fact and vote as is
            // The non-functionality of this check may lead to captcha being solved before the page loads, but this circumstance is quite rare
            // Extension will send message about passed captcha to a script that hasn't been injected yet, which will lead to voting hanging
            // For example, ionmc.top site loads captcha before the page is loaded
            if (tab.status != null && tab.status !== 'complete') return
            await chrome.tabs.sendMessage(details.tabId, {sendProject: true, project, settings})
        } catch (error) {
            catchTabError(error, project)
        }
    }
}

async function catchTabError(error, project) {
    if (error.message !== 'The frame was removed.' && !error.message.includes('No frame with id') && error.message !== 'The tab was closed.' && !error.message.includes('PrecompiledScript.executeInGlobal')/*For FireFox we ignore this error*/ && !error.message.includes('Could not establish connection. Receiving end does not exist') && !error.message.includes('The message port closed before a response was received') && (!error.message.includes('Frame with ID') && !error.message.includes('was removed'))) {
        project = await db.get('projects', project.key)
        let message = error.message
        if (message.includes('This page cannot be scripted due to an ExtensionsSettings policy')) {
            message += ' Try this solution: https://github.com/Serega007RU/Auto-Vote-Rating/wiki/Problems-with-Opera'
        }
        console.error(getProjectPrefix(project, true), error.message)
        sendNotification(getProjectPrefix(project, false), error.message, 'error', 'openProject_' + project.key)
        project.error = message
        updateValue('projects', project)
    }
}

const tabsOnRemovedListener = async function(tabId) {
    await initializeFunc
    let opened = openedProjects.get(tabId)
    if (!opened) return
    endVote({closedTab: true}, {tab: {id: tabId}}, opened)
}

const webRequestOnCompletedListener = async function(details) {
    await initializeFunc
    let opened = openedProjects.get(details.tabId)
    if (!opened) return

    // Sometimes some projects intentionally return error in status code, we have no choice but to ignore all errors, more details https://discord.com/channels/371699266747629568/760393040174120990/1053016256535593022
    if (allProjects[opened.rating].ignoreErrors?.()) return

    if (details.type === 'main_frame' && (details.statusCode < 200 || details.statusCode > 299)) {
        if (details.statusCode === 503 || details.statusCode === 403) { // If CloudFlare check
            opened.countInject--
            db.put('other', openedProjects, 'openedProjects')
        } else {
            const sender = {tab: {id: details.tabId}, url: details.url}
            endVote({errorVote: [String(details.statusCode), details.url]}, sender, opened)
        }
    }
}

const webRequestOnErrorOccurredListener = async function (details) {
    await initializeFunc
    // noinspection JSUnresolvedVariable
    /*if ((details.initiator && details.initiator.includes(self.location.hostname) || (details.originUrl && details.originUrl.includes(self.location.hostname))) && fetchProjects.has(details.requestId)) {
        let project = fetchProjects.get(details.requestId)
        endVote({errorVoteNetwork: [details.error, details.url]}, null, project)
    } else */if (openedProjects.has(details.tabId)) {
        if (details.type === 'main_frame' || details.url.match(/hcaptcha.com\/captcha\/*/) || details.url.match(/https?:\/\/(.+?\.)?google.com\/recaptcha\/*/) || details.url.match(/https?:\/\/(.+?\.)?recaptcha.net\/recaptcha\/*/) || details.url.match(/https:\/\/challenges.cloudflare.com\/*/)) {
            const opened = openedProjects.get(details.tabId)
            if (
                //Chrome
                details.error.includes('net::ERR_ABORTED') || details.error.includes('net::ERR_CONNECTION_RESET') || details.error.includes('net::ERR_NETWORK_CHANGED') || details.error.includes('net::ERR_CACHE_MISS') || details.error.includes('net::ERR_BLOCKED_BY_CLIENT') || details.error.includes('net::ERR_QUIC_PROTOCOL_ERROR')
                //FireFox
                || details.error.includes('NS_BINDING_ABORTED') || details.error.includes('NS_ERROR_NET_ON_RESOLVED') || details.error.includes('NS_ERROR_NET_ON_RESOLVING') || details.error.includes('NS_ERROR_NET_ON_WAITING_FOR') || details.error.includes('NS_ERROR_NET_ON_CONNECTING_TO') || details.error.includes('NS_ERROR_FAILURE') || details.error.includes('NS_ERROR_DOCSHELL_DYING') || details.error.includes('NS_ERROR_NET_ON_TRANSACTION_CLOSE')) {
                // console.warn(getProjectPrefix(project, true), details.error)
                return
            }
            const sender = {tab: {id: details.tabId}, url: details.url}
            endVote({errorVoteNetwork: [details.error, details.url]}, sender, opened)
        }
    }
}

const webNavigationOnErrorOccurredListener = async function (details) {
    await initializeFunc
    if (openedProjects.has(details.tabId)) {
        if (details.frameId === 0 || details.url.match(/hcaptcha.com\/captcha\/*/) || details.url.match(/https?:\/\/(.+?\.)?google.com\/recaptcha\/*/) || details.url.match(/https?:\/\/(.+?\.)?recaptcha.net\/recaptcha\/*/) || details.url.match(/https:\/\/challenges.cloudflare.com\/*/)) {
            const opened = openedProjects.get(details.tabId)
            if (
                //Chrome
                details.error.includes('net::ERR_ABORTED') || details.error.includes('net::ERR_CONNECTION_RESET') || details.error.includes('net::ERR_NETWORK_CHANGED') || details.error.includes('net::ERR_CACHE_MISS') || details.error.includes('net::ERR_BLOCKED_BY_CLIENT')
                //FireFox
                || details.error.includes('NS_BINDING_ABORTED') || details.error.includes('NS_ERROR_NET_ON_RESOLVED') || details.error.includes('NS_ERROR_NET_ON_RESOLVING') || details.error.includes('NS_ERROR_NET_ON_WAITING_FOR') || details.error.includes('NS_ERROR_NET_ON_CONNECTING_TO') || details.error.includes('NS_ERROR_FAILURE') || details.error.includes('NS_ERROR_DOCSHELL_DYING') || details.error.includes('NS_ERROR_NET_ON_TRANSACTION_CLOSE')) {
                // console.warn(getProjectPrefix(project, true), details.error)
                return
            }
            const sender = {tab: {id: details.tabId}, url: details.url}
            endVote({errorVoteNetwork: [details.error, details.url]}, sender, opened)
        }
    }
}

// Listener registration and deregistration is done to optimize extension background process
// Extension background process wakes up too often unnecessarily during web surfing (when user is using the browser)
// Therefore, if voting is not currently happening - we disable all these listeners and sleep
// If voting starts again - we register the listeners back during auto-voting
function updateListeners(enable) {
    if (settings?.debug) console.log('Listener registration, enabling', enable, 'openedProjects.size', openedProjects.size, 'openedProjects', openedProjects)
    if (enable) {
        if (!chrome.webNavigation.onErrorOccurred.hasListeners()) {
            if (settings?.debug) console.log('Registering listener webNavigation.onErrorOccurred')
            chrome.webNavigation.onErrorOccurred.addListener(webNavigationOnErrorOccurredListener)
        }
        if (!chrome.webNavigation.onCommitted.hasListeners()) {
            if (settings?.debug) console.log('Registering listener webNavigation.onCommitted')
            chrome.webNavigation.onCommitted.addListener(webNavigationOnCommittedListener)
        }
        if (!chrome.webNavigation.onCompleted.hasListeners()) {
            if (settings?.debug) console.log('Registering listener webNavigation.onCompleted')
            chrome.webNavigation.onCompleted.addListener(webNavigationOnCompletedListener)
        }
        if (!chrome.tabs.onRemoved.hasListeners()) {
            if (settings?.debug) console.log('Registering listener tabs.onRemoved')
            chrome.tabs.onRemoved.addListener(tabsOnRemovedListener)
        }
        if (!chrome.webRequest.onCompleted.hasListeners()) {
            if (settings?.debug) console.log('Registering listener webRequest.onCompleted')
            chrome.webRequest.onCompleted.addListener(webRequestOnCompletedListener, {urls: ['<all_urls>']})
        }
        if (!chrome.webRequest.onErrorOccurred.hasListeners()) {
            if (settings?.debug) console.log('Registering listener webRequest.onErrorOccurred')
            chrome.webRequest.onErrorOccurred.addListener(webRequestOnErrorOccurredListener, {urls: ['<all_urls>']})
        }
    } else {
        chrome.webNavigation.onErrorOccurred.removeListener(webNavigationOnErrorOccurredListener)
        chrome.webNavigation.onCommitted.removeListener(webNavigationOnCommittedListener)
        chrome.webNavigation.onCompleted.removeListener(webNavigationOnCompletedListener)
        chrome.tabs.onRemoved.removeListener(tabsOnRemovedListener)
        chrome.webRequest.onCompleted.removeListener(webRequestOnCompletedListener)
        chrome.webRequest.onErrorOccurred.removeListener(webRequestOnErrorOccurredListener)
    }
}

// Since Service Worker can sleep right during voting, we register listeners right at startup anyway
// After database initialization, if it's detected that we're not voting now and there's no need to vote - we deregister the listeners
updateListeners(true)

// async function _fetch(url, options, project) {
//     let listener
//     const removeListener = ()=>{
//         if (listener) {
//             chrome.webRequest.onBeforeRequest.removeListener(listener)
//             listener = null
//         }
//     }
//
//     listener = (details)=>{
//         //Да это костыль, а есть другой адекватный вариант достать requestId или хотя бы код ошибки net::ERR из fetch запроса?
//         // noinspection JSUnresolvedVariable
//         if ((details.initiator && details.initiator.includes(self.location.hostname) || (details.originUrl && details.originUrl.includes(self.location.hostname))) && details.url.includes(url)) {
//             fetchProjects.set(details.requestId, project)
//             removeListener()
//         }
//     }
//     chrome.webRequest.onBeforeRequest.addListener(listener, {urls: ['<all_urls>']})
//
//     if (!options) options = {}
//
//     try {
//         return await fetch(url, options)
//     } catch(error) {
//         throw error
//     } finally {
//         removeListener()
//     }
// }

//Listener for messages and errors
chrome.runtime.onMessage.addListener(function(request, sender, sendResponse) {
    // noinspection JSIgnoredPromiseFromCall
    onRuntimeMessage(request, sender, sendResponse)
    if (request.projectDeleted || request.projectRestart) {
        return true
    }
})

let fakeIdToId = {};
async function onRuntimeMessage(request, sender, sendResponse) {
    if (request.reloadCaptcha) {
        // noinspection JSVoidFunctionReturnValueUsed,JSCheckFunctionSignatures
        const frames = await chrome.webNavigation.getAllFrames({tabId: sender.tab.id})
        for (const frame of frames) {
            // noinspection JSUnresolvedVariable
            if (frame.url.match(/https?:\/\/(.+?\.)?google.com\/recaptcha\/api.\/anchor*/) || frame.url.match(/https?:\/\/(.+?\.)?recaptcha.net\/recaptcha\/api.\/anchor*/) || frame.url.match(/https?:\/\/(.+?\.)?google.com\/recaptcha\/enterprise\/anchor*/)) {
                function reload() {
                    document.location.reload()
                }

                if (settings.debug) { // noinspection JSUnresolvedReference
                    console.log('Injecting funcReloadCaptcha to ' + frame.url)
                }
                // noinspection JSCheckFunctionSignatures,JSUnresolvedVariable
                await chrome.scripting.executeScript({target: {tabId: sender.tab.id, frameIds: [frame.frameId]}, func: reload})
            }
        }
        return
    } else if (request.captchaPassed) {
        try {
            await chrome.tabs.sendMessage(sender.tab.id, request)
        } catch (error) {
            if (!error.message.includes('Could not establish connection. Receiving end does not exist') && !error.message.includes('The message port closed before a response was received')) {
                console.warn(error.message)
            }
        }
        if (request.captchaPassed !== 'double') return
    } else if (request.HackTimer) {
        if (request.name === 'setInterval') {
            fakeIdToId[request.fakeId] = setInterval(function () {
                triggerTimer(request.name, sender, request.fakeId);
            }, request.time);
        } else if (request.name === 'clearInterval') {
            clearInterval(fakeIdToId[request.fakeId]);
            delete fakeIdToId[request.fakeId];
        } else if (request.name === 'setTimeout') {
            fakeIdToId[request.fakeId] = setTimeout(function () {
                triggerTimer(request.name, sender, request.fakeId);
                delete fakeIdToId[request.fakeId];
            }, request.time);
        } else if (request.name === 'clearTimeout') {
            clearTimeout(fakeIdToId[request.fakeId]);
            delete fakeIdToId[request.fakeId];
        }
        return
    }

    await initializeFunc

    if (request === 'checkVote') {
        checkVote()
        return
    } else if (request === 'reloadAllSettings') {
        const store = db.transaction('other', 'readwrite').store
        settings = await store.get('settings')
        generalStats = await store.get('generalStats')
        todayStats = await store.get('todayStats')
        for (const[key,value] of openedProjects) {
            openedProjects.delete(key)
            tryCloseTab(key, value, 0)
        }
        await store.put(openedProjects, 'openedProjects')
        reloadAllAlarms()
        checkVote()
        return
    } else if (request === 'reloadSettings') {
        settings = await db.get('other', 'settings')
        return
    } else if (request.projectDeleted) {
        const transaction = db.transaction(['projects', 'other'], 'readwrite')
        let nowVoting = false
        //If this tab was already open, close it
        for (const[key,value] of openedProjects) {
            if (request.projectDeleted.key === value.key) {
                if (key === 'start_' + request.projectDeleted.key) {
                    sendResponse('reject')
                    return
                }
                nowVoting = true
                openedProjects.delete(key)
                tryCloseTab(key, request.projectDeleted, 0)
                await transaction.objectStore('other').put(openedProjects, 'openedProjects')
                break
            }
        }
        await transaction.objectStore('projects').delete(request.projectDeleted.key)
        await chrome.alarms.clear(String(request.projectDeleted.key))
        if (nowVoting) {
            checkVote()
            console.log(getProjectPrefix(request.projectDeleted, true), chrome.i18n.getMessage('projectDeleted'))
        }
        sendResponse('success')
        return
    } else if (request.projectRestart) {
        const transaction = db.transaction(['projects', 'other'], 'readwrite')
        for (const[key,value] of openedProjects) {
            if (request.projectRestart.key === value.key) {
                if (request.confirmed) {
                    openedProjects.delete(key)
                    transaction.objectStore('other').put(openedProjects, 'openedProjects')
                    tryCloseTab(key, request.projectRestart, 0)
                    console.log(getProjectPrefix(request.projectRestart, true), chrome.i18n.getMessage('canceledVote'))
                } else {
                    sendResponse('confirmNow')
                    return
                }
            }
        }
        for (const[key,value] of openedProjects) {
            if (request.projectRestart.rating === value.rating || settings.disabledOneVote) {
                if (request.confirmed) {
                    openedProjects.delete(key)
                    await transaction.objectStore('other').put(openedProjects, 'openedProjects')
                    const project = await transaction.objectStore('projects').get(value.key)
                    tryCloseTab(key, project, 0)
                    console.log(getProjectPrefix(project, true), chrome.i18n.getMessage('canceledVote'))
                } else {
                    sendResponse('confirmQueue')
                    return
                }
            }
        }

        await chrome.alarms.clear(String(request.projectRestart.key))
        request.projectRestart.time = null
        await updateValue('projects', request.projectRestart)
        console.log(getProjectPrefix(request.projectRestart, true), chrome.i18n.getMessage('projectRestarted'))
        checkOpen(request.projectRestart)
        checkVote()
        sendResponse('success')
        return
    }

    if (request.changeProject) {
        updateValue('projects', request.changeProject)
        return
    }

    if (!openedProjects.has(sender.tab.id)) {
        console.warn('A double attempt to complete the vote? chrome.runtime.onMessage', JSON.stringify(request), JSON.stringify(sender))
        return
    }

    let opened = openedProjects.get(sender.tab.id)
    if (request.captcha || request.authSteam || request.discordLogIn || request.auth || request.requiredConfirmTOS || (request.errorCaptcha && !request.restartVote) || request.restartVote === false || request.captchaPassed === 'double') {//If requires manual captcha solving
        const project = await db.get('projects', opened.key)
        let message
        if (request.captcha) {
            message = chrome.i18n.getMessage('requiresCaptcha')
        } else if (request.captchaPassed === 'double') {
            message = chrome.i18n.getMessage('captchaPassedDouble')
        } else if (request.message) {
            message = request.message
        } else {
            if (Object.values(request)[0] !== true) {
                message = chrome.i18n.getMessage(Object.keys(request)[0], Object.values(request)[0])
            } else {
                message = chrome.i18n.getMessage(Object.keys(request)[0])
            }
        }
        if (!(request.captcha && settings.disabledWarnCaptcha)) {
            console.warn(getProjectPrefix(project, true), message)
            sendNotification(getProjectPrefix(project, false), message, 'warn', 'openTab_' + sender.tab.id)
            project.error = message
        }
        updateValue('projects', project)
    } else {
        endVote(request, sender, opened)
    }
}

async function triggerTimer(name, sender, fakeId) {
    try {
        await chrome.tabs.sendMessage(sender.tab.id, {HackTimer: true, fakeId}, {documentId: sender.documentId, frameId: sender.frameId});
    } catch (error) {
        if (name === 'setInterval') clearInterval(fakeIdToId[fakeId]);
        delete fakeIdToId[fakeId];
    }
}

async function tryOpenTab(request, project, attempt) {
    try {
        return await chrome.tabs.create(request)
    } catch (error) {
        if (error.message === 'Tabs cannot be edited right now (user may be dragging a tab).' && attempt < 3) {
            await wait(500)
            return await tryOpenTab(request, project, ++attempt)
        }
        endVote({errorOpenTab: error.message}, null, project)
        return null
    }
}

async function tryCloseTab(tabId, project, attempt) {
    if (!Number.isInteger(tabId)) return
    try {
        await chrome.tabs.remove(tabId)
    } catch (error) {
        if (error.message === 'Tabs cannot be edited right now (user may be dragging a tab).' && attempt < 3) {
            await wait(500)
            await tryCloseTab(tabId, project, ++attempt)
            return
        }
        if (!error.message.includes('No tab with id')) {
            console.warn(getProjectPrefix(project, true), error.message)
            sendNotification(getProjectPrefix(project, false), error.message, 'error', 'openProject_' + project.key)
        }
    }
}

async function tryGroupTabs(options, attempt) {
    try {
        return await chrome.tabs.group(options)
    } catch (error) {
        if (error.message === 'Tabs cannot be edited right now (user may be dragging a tab).' && attempt < 3) {
            await wait(500)
            return await tryGroupTabs(options, ++attempt)
        }
        throw error
    }
}

//Completes voting, if there's an error, processes it
async function endVote(request, sender, project) {
    let timeout = settings.timeout

    let opened
    for (const [tab,value] of openedProjects) {
        if (project.key === value.key) {
            if (!Number.isInteger(tab) && !tab.startsWith('background_') && !tab.startsWith('start_')) {
                console.warn('A double attempt to complete the vote? endVote, has openedProjects', JSON.stringify(request), JSON.stringify(sender), JSON.stringify(project))
                return
            } else {
                opened = value
                if (opened.randomize) {
                    timeout += Math.floor(Math.random() * (60000 - 10000) + 10000)
                }
                opened.timeoutQueue = Date.now() + timeout

                delete opened.nextAttempt
                delete opened.countInject

                openedProjects.set('queue_' + opened.key, opened)
                openedProjects.delete(tab)
                db.put('other', openedProjects, 'openedProjects')
            }
            break
        }
    }
    if (!opened) {
        console.warn('A double attempt to complete the vote? endVote, not found openedProjects', JSON.stringify(request), JSON.stringify(sender), JSON.stringify(project))
        return
    }

    project = await db.get('projects', project.key)

    if (!request.successfully && request.later == null) {
        if (sender?.url || request.url) {
            const url = sender?.url || request.url
            const domain = getDomainWithoutSubdomain(url)
            // Если мы попали не по адресу, ну значит не надо отсылать отчёт об ошибке
            if (domain !== project.rating) {
                request.incorrectDomain = domain
            }
        }
    }

    if (sender && !request.closedTab) {
        if (!request.successfully && request.later == null) {
            if (!settings.disableCloseTabsOnError) tryCloseTab(sender.tab.id, project, 0)
        } else {
            if (!settings.disableCloseTabsOnSuccess) tryCloseTab(sender.tab.id, project, 0)
        }
    }

    // for (const[key,value] of fetchProjects) {
    //     if (value.key === project.key) {
    //         fetchProjects.delete(key)
    //     }
    // }

    // Re-fetch project as it could have changed during report sending or remote code usage
    project = await db.get('projects', project.key)

    //If everything is successful
    let sendMessage
    if (request.successfully || request.later != null) {
        let time = new Date()
        if (project.rating === 'Custom' || ((project.timeout != null || project.timeoutHour != null) && !Number.isInteger(request.later) && !(project.lastDayMonth && new Date(time.getFullYear(), time.getMonth(), time.getDay() + 1).getMonth() === new Date().getMonth()))) {
            if (project.timeoutHour != null) {
                if (project.timeoutMinute == null) project.timeoutMinute = 0
                if (project.timeoutSecond == null) project.timeoutSecond = 0
                if (project.timeoutMS == null) project.timeoutMS = 0

                let month = time.getMonth()
                let date = time.getDate()

                let needCalculateDate = true
                if (project.timeoutWeek != null) {
                    // https://stackoverflow.com/a/11789820/11235240
                    const distance = (project.timeoutWeek + 7 - time.getDay()) % 7
                    if (distance > 0) {
                        needCalculateDate = false
                        date += distance
                    }
                } else if (project.timeoutMonth != null) {
                    if (time.getDate() !== project.timeoutMonth) {
                        needCalculateDate = false
                        if (time.getDate() > project.timeoutMonth) month += 1
                        date = project.timeoutMonth
                    }
                }
                if (needCalculateDate) {
                    if (time.getHours() > project.timeoutHour || (time.getHours() === project.timeoutHour && time.getMinutes() >= project.timeoutMinute)) {
                        if (project.timeoutWeek != null) {
                            date += 7
                        } else if (project.timeoutMonth != null) {
                            month += 1
                            date = project.timeoutMonth
                        } else {
                            date += 1
                        }
                    }
                }

                time = new Date(time.getFullYear(), month, date, project.timeoutHour, project.timeoutMinute, project.timeoutSecond, project.timeoutMS)
            } else {
                time.setUTCMilliseconds(time.getUTCMilliseconds() + project.timeout)
            }
        } else if (request.later && Number.isInteger(request.later)) {
            let needSetTime = true
            if (allProjects[project.rating]?.limitedCountVote?.()) {
                project.countVote = project.countVote + 1
                if (project.countVote >= project.maxCountVote) {
                    needSetTime = false
                    time = new Date(time.getFullYear(), time.getMonth(), time.getDate() + 1, 0, (project.priority ? 0 : 10), 0, 0)
                }
            }
            if (needSetTime) {
                time = new Date(request.later)
            }
        } else {
            const timeoutRating = allProjects[project.rating]?.timeout?.(project)
            if (Number.isInteger(request.successfully)) {
                time = new Date(request.successfully)
            } else if (!timeoutRating) {
                //If timeout is unknown, set default +24 hours
                time.setUTCDate(time.getUTCDate() + 1)
            } else if (timeoutRating.week != null) {
                let date = time.getUTCDate()
                // https://stackoverflow.com/a/11789820/11235240
                const distance = (timeoutRating.week + 7 - time.getUTCDay()) % 7
                if (distance > 0) {
                    date += distance
                } else {
                    if (time.getUTCHours() >= timeoutRating.hour) {
                        date += 7
                    }
                }
                time = new Date(Date.UTC(time.getUTCFullYear(), time.getUTCMonth(), date, timeoutRating.hour, (project.priority ? 0 : 10), 0, 0))
            } else if (timeoutRating.month != null) {
                let month = time.getUTCMonth()
                let date = time.getUTCDate()
                if (time.getUTCDate() !== timeoutRating.month) {
                    if (time.getUTCDate() > timeoutRating.month) month += 1
                    date = timeoutRating.month
                } else {
                    if (time.getUTCHours() >= timeoutRating.hour) {
                        month += 1
                        date = timeoutRating.month
                    }
                }
                time = new Date(Date.UTC(time.getUTCFullYear(), month, date, timeoutRating.hour, (project.priority ? 0 : 10), 0, 0))
            } else if (timeoutRating.hour != null) {
                //Ratings with timeout that resets once a day at a specific hour
                let date = time.getUTCHours() >= timeoutRating.hour ? time.getUTCDate() + 1 : time.getUTCDate()
                time = new Date(Date.UTC(time.getUTCFullYear(), time.getUTCMonth(), date, timeoutRating.hour, (project.priority ? 0 : 10), 0, 0))
            } else if (timeoutRating.hours != null) {
                let needSetTime = true
                //Ratings with timeout that resets after a certain period of time from the last vote
                if (allProjects[project.rating]?.limitedCountVote?.()) {
                    project.countVote = project.countVote + 1
                    if (project.countVote >= project.maxCountVote) {
                        needSetTime = false
                        time = new Date(time.getFullYear(), time.getMonth(), time.getDate() + 1, 0, (project.priority ? 0 : 10), 0, 0)
                        project.countVote = 0
                    }
                }
                if (needSetTime) {
                    let hours = time.getHours() + timeoutRating.hours
                    let minutes = time.getMinutes()
                    let seconds = time.getSeconds()
                    let milliseconds = time.getMilliseconds()
                    if (timeoutRating.minutes != null) minutes += timeoutRating.minutes
                    // noinspection JSUnresolvedVariable
                    if (timeoutRating.seconds != null) seconds += timeoutRating.seconds
                    // noinspection JSUnresolvedVariable
                    if (timeoutRating.milliseconds != null) milliseconds += timeoutRating.milliseconds
                    time = new Date(time.getFullYear(), time.getMonth(), time.getDate(), hours, minutes, seconds, milliseconds)
                }
            }
        }

        time = time.getTime()
        project.time = time

        if (project.randomize) {
            if (project.randomize.min == null) {
                project.randomize = {}
                project.randomize.min = 0
                project.randomize.max = 43200000
            }
            project.time = project.time + Math.floor(Math.random() * (project.randomize.max - project.randomize.min) + project.randomize.min)
        } else if ((project.rating === 'topcraft.ru' || project.rating === 'topcraft.club' || project.rating === 'mctop.su' || (project.rating === 'minecraftrating.ru' && project.listing === 'projects')) && !project.priority && project.timeoutHour == null) {
            //Default randomization (within 5-10 minutes) for poor TopCraft/McTOP which is easily DDoSed by mass automatic voting
            project.time = project.time + Math.floor(Math.random() * (600000 - 300000) + 300000)
        }

        delete project.error
        delete project.warn

        if (request.successfully) {
            if (typeof request.successfully === 'string') {
                project.warn = request.successfully
                sendMessage = chrome.i18n.getMessage('successAutoVoteWarn', request.successfully)
            } else {
                sendMessage = chrome.i18n.getMessage('successAutoVote')
            }

            sendNotification(getProjectPrefix(project, false), sendMessage, 'info', 'openProject_' + project.key)

            project.stats.successVotes++
            project.stats.monthSuccessVotes++
            project.stats.lastSuccessVote = Date.now()

            generalStats.successVotes++
            generalStats.monthSuccessVotes++
            generalStats.lastSuccessVote = Date.now()
            todayStats.successVotes++
            todayStats.lastSuccessVote = Date.now()
        } else {
            if (typeof request.later === 'string') {
                project.warn = request.later
                sendMessage = chrome.i18n.getMessage('alreadyVotedWarn', request.later)
            } else {
                sendMessage = chrome.i18n.getMessage('alreadyVoted')
            }

            sendNotification(getProjectPrefix(project, false), sendMessage, project.warn ? 'warn' : 'info', 'openProject_' + project.key)

            project.stats.laterVotes++

            generalStats.laterVotes++
            todayStats.laterVotes++
        }
        console.log(getProjectPrefix(project, true), sendMessage + ', ' + chrome.i18n.getMessage('timeStamp') + ' ' + project.time)
        //If error
    } else {
        let message
        if (!request.message) {
            const name = Object.keys(request)[0]
            if (Object.values(request)[0] === true) {
                message = chrome.i18n.getMessage(name)
            } else {
                message = chrome.i18n.getMessage(name, Object.values(request)[0])
            }
            if (request.usedTranslator && name !== 'usedTranslator') {
                message += ' ' + chrome.i18n.getMessage('usedTranslator')
            }
        } else {
            message = chrome.i18n.getMessage('siteError', request.message)
        }
        if (message.length === 0) message = chrome.i18n.getMessage('emptyError')
        if (request.incorrectDomain) {
            message += ' Incorrect domain ' + request.incorrectDomain
        }
        let retryCoolDown
        if (request.retryCoolDown) {
            retryCoolDown = request.retryCoolDown
        } else if ((request.errorVote && request.errorVote[0] === '404') || (request.message && project.rating === 'wargm.ru' && project.randomize)) {
            retryCoolDown = 21600000
        } else if (request.closedTab) {
            retryCoolDown = 60000
        } else {
            retryCoolDown = settings.timeoutError
        }

        sendMessage = message + '. ' + chrome.i18n.getMessage('errorNextVote', (Math.round(retryCoolDown / 1000 / 60 * 100) / 100).toString())

        if (project.randomize) {
            retryCoolDown = retryCoolDown + Math.floor(Math.random() * 900000)
        }
        project.time = Date.now() + retryCoolDown
        project.error = message
        console.error(getProjectPrefix(project, true), sendMessage + ', ' + chrome.i18n.getMessage('timeStamp') + ' ' + project.time)
        if (!(request.errorVote && request.errorVote[0].charAt(0) === '5')) sendNotification(getProjectPrefix(project, false), sendMessage, 'error', 'openProject_' + project.key)

        project.stats.errorVotes++

        generalStats.errorVotes++
        todayStats.errorVotes++
    }

    await db.put('other', generalStats, 'generalStats')
    await db.put('other', todayStats, 'todayStats')
    await updateValue('projects', project)

    await chrome.alarms.clear('nextAttempt_' + project.key)
    if (project.time != null && project.time > Date.now()) {
        let create2 = true
        let when = project.time
        if (when - Date.now() < 65000) when = Date.now() + 65000
        const alarms = await chrome.alarms.getAll()
        for (const alarm of alarms) {
            // noinspection JSCheckFunctionSignatures
            if (!isNaN(alarm.name) && alarm.scheduledTime === when) {
                create2 = false
                break
            }
        }
        if (create2) {
            try {
                await chrome.alarms.create(String(project.key), {when})
            } catch (error) {
                console.warn(getProjectPrefix(project, true), 'Ошибка при создании chrome.alarms', error.message)
            }
        }
    }

    async function removeQueue() {
        for (const [tab,value] of openedProjects) {
            if (tab.startsWith?.('queue_') && project.key === value.key) {
                openedProjects.delete(tab)
            }
        }
        db.put('other', openedProjects, 'openedProjects')
        checkVote()
    }

    setTimeout(()=>{
        removeQueue()
    }, timeout)

    // TODO We can't be sure that setTimeout in Service Worker will work 100%, so we create chrome.alarm just in case
    let alarmTimeout = timeout
    if (alarmTimeout < 65000) alarmTimeout = 65000
    try {
        await chrome.alarms.create('checkVote', {when: Date.now() + alarmTimeout})
    } catch (error) {
        console.warn(getProjectPrefix(project, true), 'Error when creating chrome.alarms', error.message)
    }
}

//Notification sender
function sendNotification(title, message, type, notificationId) {
    if (!message) message = ''
    if (!notificationId) notificationId = ''

    if (settings?.disabledNotifStart && type === 'start') return
    if (settings?.disabledNotifInfo && type === 'info') return

    if (type === 'warn' || type === 'error') {
        (async () => {
            try {
                await chrome.runtime.sendMessage({notification: {title, message, type, notificationId}})
            } catch (error) {
                if (!error.message.includes('Could not establish connection. Receiving end does not exist') && !error.message.includes('The message port closed before a response was received')) {
                    console.warn(error.message)
                }
            }
        })()
    }

    if (settings?.disabledNotifWarn && type === 'warn') return
    if (settings?.disabledNotifError && type === 'error') return

    let notification = {
        type: 'basic',
        iconUrl: 'images/icon128.png',
        title: title,
        message: message
    }
    chrome.notifications.create(notificationId, notification, function() {})
}
chrome.notifications.onClicked.addListener(async function (notificationId) {
    if (notificationId.startsWith('openTab_')) {
        try {
            const tabId = Number(notificationId.replace('openTab_', ''))
            if (!tabId) return
            const tab = await chrome.tabs.update(tabId, {active: true})
            if (!tab) return
            await chrome.windows.update(tab.windowId, {focused: true})
        } catch (error) {
            if (!error.message.includes('No tab with id')) {
                console.warn('Error when focusing on tab', error.message)
            }
        }
    } else if (notificationId.startsWith('openProject_')) {
        try {
            const projectKey = Number(notificationId.replace('openProject_', ''))
            const found = await db.count('projects', projectKey)
            if (!found) return
            await openOptionsPage()
            await chrome.runtime.sendMessage({openProject: projectKey})
        } catch (error) {
            console.warn('Error opening settings with specific project', error.message)
        }
    } else if (notificationId.startsWith('openSettings')) {
        await chrome.runtime.openOptionsPage()
    }
})

async function openOptionsPage() {
    await chrome.runtime.openOptionsPage()
    // Wild workaround for waiting for tab to load, we can't adequately pass necessary data to settings, so have to do this workaround
    const tab = await chrome.tabs.query({active: true, lastFocusedWindow: true})
    if (!tab.length) return
    if (tab[0].status !== 'complete') {
        for (let i = 0; i < 9; i++) {
            await wait(250)
            const t = await chrome.tabs.get(tab[0].id)
            if (t.status === 'complete') break
        }
    }
}

function getProjectPrefix(project, detailed) {
    let text = ''
    if (project.nick && project.nick !== '') text += ' – ' + project.nick
    if (detailed && project.game && project.game !== '') text += ' – ' + project.game
    if (detailed) {
        if (project.id && project.id !== '') text += ' – ' + project.id
        if (project.name && project.name !== '') text += ' – ' + project.name
    } else {
        if (project.name && project.name !== '') {
            text += ' – ' + project.name
        } else if (project.id && project.id !== '') {
            text += ' – ' + project.id
        }
    }
    if (text === '') {
        return '[' + project.rating + ']'
    } else {
        text = text.replace(' – ', '')
        return '[' + project.rating + '] ' + text
    }
}

function wait(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

async function updateValue(objStore, value) {
    const store = db.transaction(objStore, 'readwrite').store
    const found = await store.count(value.key)
    if (found) {
        await store.put(value, value.key);
        (async () => {
            try {
                await chrome.runtime.sendMessage({updateValue: objStore, value})
            } catch (error) {
                if (!error.message.includes('Could not establish connection. Receiving end does not exist') && !error.message.includes('The message port closed before a response was received')) {
                    console.error(error.message)
                }
            }
        })();
    } else {
        console.warn('The ' + objStore + ' could not be found, it may have been deleted', JSON.stringify(value))
    }
}

chrome.runtime.onInstalled.addListener(async function(details) {
    await initializeFunc
    // noinspection JSUnresolvedReference
    if (!settings.operaAttention2 && (navigator?.userAgentData?.brands?.[0]?.brand === 'Opera' || (!!self.opr && !!opr.addons) || !!self.opera || navigator.userAgent.indexOf(' OPR/') >= 0)) {
        chrome.runtime.openOptionsPage()
        return
    }
    if (details.reason === 'install') {
        await openOptionsPage()
        chrome.runtime.sendMessage({installed: true})
    } else if (details.reason === 'update') {
        checkVote()
    }/* else if (details.reason === 'update' && details.previousVersion && (new Version(details.previousVersion)).compareTo(new Version('6.0.0')) === -1) {

    }*/
})

// function Version(s){
//   this.arr = s.split('.').map(Number)
// }
// Version.prototype.compareTo = function(v){
//     for (let i=0; ;i++) {
//         if (i>=v.arr.length) return i>=this.arr.length ? 0 : 1
//         if (i>=this.arr.length) return -1
//         const diff = this.arr[i]-v.arr[i]
//         if (diff) return diff>0 ? 1 : -1
//     }
// }


/* Store the original log functions. */
console._log = console.log
console._info = console.info
console._warn = console.warn
console._error = console.error
console._debug = console.debug

/* Redirect all calls to the collector. */
console.log = function () { return console._intercept('log', arguments) }
console.info = function () { return console._intercept('info', arguments) }
console.warn = function () { return console._intercept('warn', arguments) }
console.error = function () { return console._intercept('error', arguments) }
console.debug = function () { return console._intercept('debug', arguments) }

/* Give the developer the ability to intercept the message before letting
   console-history access it. */
console._intercept = function (type, args) {
    // Your own code can go here, but the preferred method is to override this
    // function in your own script, and add the line below to the end or
    // begin of your own 'console._intercept' function.
    // REMEMBER: Use only underscore console commands inside _intercept!
    console._collect(type, args)
}

console._collect = function (type, args) {
    const time = new Date().toLocaleString().replace(',', '')

    if (!type) type = 'log'

    if (!args || args.length === 0) return

    console['_' + type].apply(console, args)

    let log = '[' + time + ' ' + type.toUpperCase() + ']:'

    for (let arg of args) {
        if (arg?.stack) {
            log += ' ' + arg.stack
        } else {
            if (typeof arg != 'string') arg = JSON.stringify(arg)
            log += ' ' + arg
        }
    }

    if (dbLogs) dbLogs.add('logs', log)
}

/*
Открытый репозиторий:
https://github.com/Serega007RU/Auto-Vote-Rating/
*/