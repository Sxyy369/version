// Global State
let socket;
let obsChart;
let amap = null;
let mapMarker = null;
let lastLogSignature = "";
let alarmAudioCtx = null;
let flashInterval = null;

function playAlarmBeep() {
    if (!alarmAudioCtx) {
        alarmAudioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
    if (alarmAudioCtx.state === 'suspended') alarmAudioCtx.resume();

    const osc = alarmAudioCtx.createOscillator();
    const gainNode = alarmAudioCtx.createGain();

    osc.type = 'square';
    osc.frequency.setValueAtTime(800, alarmAudioCtx.currentTime);
    osc.frequency.setValueAtTime(1200, alarmAudioCtx.currentTime + 0.1);

    gainNode.gain.setValueAtTime(0, alarmAudioCtx.currentTime);
    gainNode.gain.linearRampToValueAtTime(1, alarmAudioCtx.currentTime + 0.05);
    gainNode.gain.linearRampToValueAtTime(0, alarmAudioCtx.currentTime + 0.5);

    osc.connect(gainNode);
    gainNode.connect(alarmAudioCtx.destination);
    osc.start();
    osc.stop(alarmAudioCtx.currentTime + 0.5);
}

function triggerAlarmEffect(msg) {
    playAlarmBeep();

    if (flashInterval) clearInterval(flashInterval);

    let isOriginal = false;
    const originalTitle = "监护端 | 智能导盲系统";
    flashInterval = setInterval(() => {
        document.title = isOriginal ? `【SOS警报】 ${msg}` : originalTitle;
        isOriginal = !isOriginal;
    }, 500);

    setTimeout(() => {
        clearInterval(flashInterval);
        document.title = originalTitle;
    }, 5000);
}

// ========== WGS-84 → GCJ-02 坐标转换 ==========
function wgs84ToGcj02(lng, lat) {
    const a = 6378245.0;
    const ee = 0.00669342162296594323;
    if (outOfChina(lng, lat)) return [lng, lat];
    let dlat = transformLat(lng - 105.0, lat - 35.0);
    let dlng = transformLng(lng - 105.0, lat - 35.0);
    const radlat = lat / 180.0 * Math.PI;
    let magic = Math.sin(radlat);
    magic = 1 - ee * magic * magic;
    const sqrtmagic = Math.sqrt(magic);
    dlat = (dlat * 180.0) / ((a * (1 - ee)) / (magic * sqrtmagic) * Math.PI);
    dlng = (dlng * 180.0) / (a / sqrtmagic * Math.cos(radlat) * Math.PI);
    return [lng + dlng, lat + dlat];
}
function transformLat(lng, lat) {
    let ret = -100.0 + 2.0 * lng + 3.0 * lat + 0.2 * lat * lat +
        0.1 * lng * lat + 0.2 * Math.sqrt(Math.abs(lng));
    ret += (20.0 * Math.sin(6.0 * lng * Math.PI) + 20.0 * Math.sin(2.0 * lng * Math.PI)) * 2.0 / 3.0;
    ret += (20.0 * Math.sin(lat * Math.PI) + 40.0 * Math.sin(lat / 3.0 * Math.PI)) * 2.0 / 3.0;
    ret += (160.0 * Math.sin(lat / 12.0 * Math.PI) + 320 * Math.sin(lat * Math.PI / 30.0)) * 2.0 / 3.0;
    return ret;
}
function transformLng(lng, lat) {
    let ret = 300.0 + lng + 2.0 * lat + 0.1 * lng * lng +
        0.1 * lng * lat + 0.1 * Math.sqrt(Math.abs(lng));
    ret += (20.0 * Math.sin(6.0 * lng * Math.PI) + 20.0 * Math.sin(2.0 * lng * Math.PI)) * 2.0 / 3.0;
    ret += (20.0 * Math.sin(lng * Math.PI) + 40.0 * Math.sin(lng / 3.0 * Math.PI)) * 2.0 / 3.0;
    ret += (150.0 * Math.sin(lng / 12.0 * Math.PI) + 300.0 * Math.sin(lng / 30.0 * Math.PI)) * 2.0 / 3.0;
    return ret;
}
function outOfChina(lng, lat) {
    return lng < 72.004 || lng > 137.8347 || lat < 0.8293 || lat > 55.8271;
}
// ========== 坐标转换 END ==========

document.addEventListener('DOMContentLoaded', () => {
    initSocket();
    initChart();
    initMap();

    // Initial calls
    updateDashboard(); // Poll immediately
    setInterval(updateDashboard, 1000); // Poll every second for stats
});

function initMap() {
    console.log("initMap called, container:", document.getElementById('amap-container'));
    if (typeof AMap !== 'undefined' && document.getElementById('amap-container')) {
        try {
            // Init map without specific center first, or a default center
            amap = new AMap.Map('amap-container', {
                zoom: 16,
                center: [116.397428, 39.90923], // Default Beijing
                resizeEnable: true
            });

            // Setup a marker
            mapMarker = new AMap.Marker({
                map: amap,
                position: [116.397428, 39.90923],
                icon: 'https://webapi.amap.com/theme/v1.3/markers/n/mark_r.png'
            });
            console.log("AMap fully initialized.");
        } catch (e) {
            console.error("Init AMap failed:", e);
        }
    } else {
        console.warn("AMap library not found or container missing.");
    }
}

function initSocket() {
    socket = io();

    socket.on('connect', () => {
        console.log("Socket Connected");
        updateConnectionStatus(true);

        // --- Geolocation Sync (Phone as Sensor) ---
        // Only run this if we are NOT the guardian, to prevent sending guardian's own location
        if (navigator.geolocation && (typeof isGuardian === 'undefined' || !isGuardian)) {
            console.log("GPS: Requesting access...");
            navigator.geolocation.watchPosition(
                (position) => {
                    // 精度过滤：>100m 的数据不可靠，丢弃
                    if (position.coords.accuracy > 100) {
                        document.getElementById('conn-text').innerText = `Inside Link: GPS精度过低 (±${Math.round(position.coords.accuracy)}m)`;
                        return;
                    }

                    // ★ WGS-84 → GCJ-02 坐标转换
                    const [gcjLon, gcjLat] = wgs84ToGcj02(position.coords.longitude, position.coords.latitude);

                    const data = {
                        lat: gcjLat,
                        lon: gcjLon,
                        acc: position.coords.accuracy
                    };
                    console.log("GPS Update (GCJ-02):", data);
                    socket.emit('update_gps', data);

                    // Update connection Text to show GPS active with accuracy
                    const acc = Math.round(data.acc);
                    document.getElementById('conn-text').innerText = `Inside Link: Connected (GPS ±${acc}m GCJ-02)`;
                },
                (error) => {
                    console.error("GPS Error:", error);
                    document.getElementById('conn-text').innerText = "Inside Link: GPS Error";
                },
                {
                    enableHighAccuracy: true,
                    maximumAge: 0, // Force fresh location, no cache
                    timeout: 20000
                }
            );
        }
    });

    socket.on('disconnect', () => {
        console.log("Socket Disconnected");
        updateConnectionStatus(false);
    });

    socket.on('connect_error', (error) => {
        console.error("Socket Error:", error);
        updateConnectionStatus(false);
    });

    socket.on('video_frame', (data) => {
        const img = document.getElementById('liveVideo');
        if (img) {
            img.style.display = 'block';
            img.src = data.image;

            // Hide "No Signal" overlay if it existed (simplification)
            const parent = img.parentElement;
            if (parent.querySelector('.no-signal-msg')) {
                parent.querySelector('.no-signal-msg').remove();
            }
        }
    });

    socket.on('guardian_gps_update', (data) => {
        console.log("Received guardian_gps_update from backend:", data);
        if (amap) {
            const newPos = [data.lon, data.lat];
            if (!mapMarker) {
                mapMarker = new AMap.Marker({
                    map: amap,
                    position: newPos,
                    icon: 'https://webapi.amap.com/theme/v1.3/markers/n/mark_r.png'
                });
            } else {
                mapMarker.setPosition(newPos);
            }
            amap.setCenter(newPos);
            console.log("Map marker moved to:", newPos);
        } else {
            console.warn("Received GPS but amap is null.");
        }
    });

    socket.on('stats_update', (data) => {
        // Real-time stats can be handled here if server emits them
    });
}

function updateConnectionStatus(isConnected) {
    const badge = document.getElementById('conn-status');
    const text = document.getElementById('conn-text');
    if (isConnected) {
        badge.classList.remove('offline');
        text.innerText = 'Inside Link: Connected';
    } else {
        badge.classList.add('offline');
        text.innerText = 'Inside Link: Disconnected';
    }
}

function initChart() {
    const ctx = document.getElementById('obsChart').getContext('2d');
    obsChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['安全区域', '一般障碍', '高危障碍'],
            datasets: [{
                data: [100, 0, 0],
                backgroundColor: ['#188038', '#f9ab00', '#d93025'], // Green, Yellow, Red
                borderWidth: 0,
                hoverOffset: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '70%',
            plugins: {
                legend: {
                    position: 'right',
                    labels: {
                        usePointStyle: true,
                        boxWidth: 8
                    }
                }
            }
        }
    });
}

// === Action Functions ===

window.bindUser = function () {
    const username = document.getElementById('bind-user-input').value;
    const msgEl = document.getElementById('bind-msg');

    if (!username) {
        msgEl.innerText = "请输入用户名";
        return;
    }

    fetch('/api/bind', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target_username: username })
    })
        .then(r => r.json())
        .then(data => {
            if (data.status === 'ok') {
                location.reload();
            } else {
                msgEl.innerText = data.message || "绑定失败";
            }
        })
        .catch(e => {
            msgEl.innerText = "网络错误";
        });
};

window.sendTTS = function () {
    const input = document.getElementById('tts-input');
    const text = input.value;
    if (!text) return;

    // Visual feedback
    const btn = document.querySelector('button[onclick="sendTTS()"]');
    const originalText = btn.innerText;
    btn.innerText = "发送中...";
    btn.disabled = true;

    fetch('/api/speak', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: text })
    })
        .finally(() => {
            input.value = '';
            btn.innerText = originalText;
            btn.disabled = false;
            // Trigger immediate fetch to show log update
            setTimeout(updateDashboard, 500);
        });
};

window.sendSOS = function () {
    if (!confirm("⚠️ 确认发送 SOS 紧急警报？\n设备将以最大音量播放警报音！")) return;

    fetch('/api/speak', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: "前方危险！立即停止！", sos: true })
    });
};

window.updateConfig = function () {
    const slider = document.getElementById('sens-slider');
    const valObj = document.getElementById('sens-val');
    const val = slider.value;

    valObj.innerText = val;

    fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sensitivity: val })
    });
};

window.toggleFullScreen = function () {
    const videoCard = document.querySelector('.video-card');
    if (!document.fullscreenElement) {
        if (videoCard.requestFullscreen) {
            videoCard.requestFullscreen();
        } else if (videoCard.webkitRequestFullscreen) {
            videoCard.webkitRequestFullscreen();
        }
    } else {
        if (document.exitFullscreen) {
            document.exitFullscreen();
        }
    }
};

window.captureSnapshot = function () {
    const img = document.getElementById('liveVideo');
    if (!img || !img.src || img.style.display === 'none') {
        alert("暂无视频画面可截图");
        return;
    }

    const canvas = document.createElement('canvas');
    canvas.width = img.naturalWidth || 640;
    canvas.height = img.naturalHeight || 480;
    const ctx = canvas.getContext('2d');

    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

    const a = document.createElement('a');
    a.href = canvas.toDataURL('image/jpeg', 0.9);
    const now = new Date();
    const pad = n => n.toString().padStart(2, '0');
    a.download = `BlindAssist_Snapshot_${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}_${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}.jpg`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
};

// === Polling & Updates ===

function updateDashboard() {
    fetch('/api/stats')
        .then(r => r.json())
        .then(data => {
            // Update Text Stats
            document.getElementById('stat-fps').innerText = data.fps || '--';
            document.getElementById('stat-latency').innerText = (data.latency || '--') + ' ms';
            document.getElementById('stat-battery').innerText = (data.battery || '--') + '%';

            // Update Logs
            renderLogs(data.logs);

            // Update Chart (Mock Logic for demo visual movement, similar to previous version)
            // Ideally backend returns specific 'risk_level' breakdown
            const safe = Math.max(0, 100 - (data.warnings_count * 2) - 10);
            const warning = data.warnings_count * 2;
            const danger = 10;

            obsChart.data.datasets[0].data = [safe, warning, danger];
            obsChart.update();
        })
        .catch(err => console.log("Stats poll error:", err));
}

function renderLogs(logs) {
    const container = document.getElementById('log-container');
    if (!logs || logs.length === 0) {
        container.innerHTML = '<div style="text-align:center; color:#9aa0a6; padding:20px;">暂无日志</div>';
        return;
    }

    const topLog = logs[0];
    const signature = topLog.time + topLog.msg;
    if (lastLogSignature && signature !== lastLogSignature) {
        if (topLog.cat === 'SOS' || topLog.cat === 'WARNING') {
            triggerAlarmEffect(topLog.msg);
        }
    }
    lastLogSignature = signature;

    // Only re-render if content changed (simple check) to avoid jitter
    // For now, simple re-render
    const html = logs.map(log => {
        // Map category to CSS class suffix
        let catClass = 'DEFAULT';
        if (log.cat === 'WARNING') catClass = 'WARNING';
        if (log.cat === 'SOS') catClass = 'SOS';
        if (log.cat === 'CONFIG') catClass = 'Config';

        return `
            <div class="log-item">
                <span class="log-time">${log.time}</span>
                <span class="log-tag ${catClass}">${log.cat}</span>
                <span class="log-msg">${log.msg}</span>
            </div>
        `;
    }).join('');

    container.innerHTML = html;
}

// === Push to Talk Audio Logic ===

let mediaRecorder;
let audioChunks = [];
let isRecording = false;

window.startRecording = async function () {
    if (isRecording) return;

    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaRecorder = new MediaRecorder(stream);

        mediaRecorder.ondataavailable = event => {
            if (event.data.size > 0) {
                audioChunks.push(event.data);
            }
        };

        mediaRecorder.onstop = async () => {
            const audioBlob = new Blob(audioChunks, { type: 'audio/webm' }); // Use webm for browser compatibility usually
            const base64Audio = await blobToBase64(audioBlob);

            // Send to server
            socket.emit('guardian_audio', {
                audio_data: base64Audio,
                timestamp: new Date().getTime()
            });

            // Clean up
            audioChunks = [];
            stream.getTracks().forEach(track => track.stop());
            console.log("Audio transmitted via WebSocket.");
        };

        audioChunks = [];
        mediaRecorder.start();
        isRecording = true;

        // UI Update
        const btn = document.getElementById('ptt-btn');
        const text = document.getElementById('ptt-text');
        btn.style.backgroundColor = 'var(--error-color)';
        text.innerText = '松开发送';

    } catch (err) {
        console.error("Error accessing microphone:", err);
        alert("无法访问麦克风，请检查浏览器权限设置。");
    }
};

window.stopRecording = function () {
    if (!isRecording || !mediaRecorder) return;

    mediaRecorder.stop();
    isRecording = false;

    // UI Update
    const btn = document.getElementById('ptt-btn');
    const text = document.getElementById('ptt-text');
    btn.style.backgroundColor = '#f9ab00'; // Back to warning yellow
    text.innerText = '按住说话';
};

function blobToBase64(blob) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onloadend = () => {
            const base64data = reader.result.split(',')[1];
            resolve(base64data);
        };
        reader.onerror = reject;
        reader.readAsDataURL(blob);
    });
}

