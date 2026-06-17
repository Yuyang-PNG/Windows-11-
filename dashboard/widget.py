from flask import Blueprint, jsonify, render_template_string
import psutil
from datetime import datetime

widget_bp = Blueprint('widget', __name__)

WIDGET_HTML = '''
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>智优进程管理器 - 小组件</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: white;
            padding: 15px;
            width: 300px;
            border-radius: 12px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.3);
        }
        .header {
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }
        .header h1 { font-size: 14px; font-weight: 600; }
        .header .version { font-size: 10px; opacity: 0.5; }
        .status-bar {
            display: flex;
            gap: 10px;
            margin-bottom: 12px;
        }
        .stat {
            flex: 1;
            background: rgba(255,255,255,0.1);
            padding: 10px;
            border-radius: 8px;
            text-align: center;
        }
        .stat-value { font-size: 20px; font-weight: bold; }
        .stat-label { font-size: 10px; opacity: 0.7; margin-top: 2px; }
        .stat.warning .stat-value { color: #fbbf24; }
        .stat.danger .stat-value { color: #ef4444; }
        .games {
            background: rgba(255,255,255,0.05);
            border-radius: 8px;
            padding: 10px;
            margin-bottom: 12px;
        }
        .games h3 { font-size: 11px; margin-bottom: 8px; opacity: 0.8; }
        .game-item {
            display: flex;
            justify-content: space-between;
            font-size: 11px;
            padding: 4px 0;
            border-bottom: 1px solid rgba(255,255,255,0.05);
        }
        .game-item:last-child { border-bottom: none; }
        .actions {
            display: flex;
            gap: 8px;
        }
        .action-btn {
            flex: 1;
            padding: 8px 6px;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 11px;
            transition: all 0.2s;
        }
        .action-btn:hover { transform: scale(1.02); opacity: 0.9; }
        .action-btn.primary { background: #4ade80; color: #000; }
        .action-btn.secondary { background: rgba(255,255,255,0.15); color: white; }
        .footer {
            margin-top: 10px;
            text-align: center;
            font-size: 9px;
            opacity: 0.4;
        }
    </style>
</head>
<body>
    <div class="header">
        <span style="font-size: 20px;">🎮</span>
        <div>
            <h1>智优进程管理器</h1>
            <div class="version">v1.2.0</div>
        </div>
    </div>
    
    <div class="status-bar">
        <div class="stat" id="cpu-stat">
            <div class="stat-value" id="cpu">0%</div>
            <div class="stat-label">CPU</div>
        </div>
        <div class="stat" id="memory-stat">
            <div class="stat-value" id="memory">0%</div>
            <div class="stat-label">内存</div>
        </div>
    </div>
    
    <div class="games">
        <h3>🎮 游戏进程 (<span id="game-count">0</span>)</h3>
        <div id="game-list">
            <div class="game-item"><span>无检测到</span><span>-</span></div>
        </div>
    </div>
    
    <div class="actions">
        <button class="action-btn primary" onclick="doAction('optimize')">⚡ 优化</button>
        <button class="action-btn secondary" onclick="doAction('games')">🎮 游戏</button>
        <button class="action-btn secondary" onclick="doAction('restore')">↩️ 恢复</button>
    </div>
    
    <div class="footer">
        最后更新: <span id="last-update">-</span>
    </div>

    <script>
        function updateStatus() {
            fetch('/api/widget/status')
                .then(r => r.json())
                .then(data => {
                    document.getElementById('cpu').textContent = data.cpu.toFixed(1) + '%';
                    document.getElementById('memory').textContent = data.memory.toFixed(1) + '%';
                    
                    // CPU状态颜色
                    const cpuStat = document.getElementById('cpu-stat');
                    cpuStat.className = 'stat' + (data.cpu > 80 ? ' danger' : data.cpu > 60 ? ' warning' : '');
                    
                    // 内存状态颜色
                    const memStat = document.getElementById('memory-stat');
                    memStat.className = 'stat' + (data.memory > 85 ? ' danger' : data.memory > 70 ? ' warning' : '');
                    
                    // 游戏列表
                    document.getElementById('game-count').textContent = data.gaming_processes.length;
                    const list = document.getElementById('game-list');
                    if (data.gaming_processes.length > 0) {
                        list.innerHTML = data.gaming_processes.map(g => 
                            `<div class="game-item">
                                <span>${g.name}</span>
                                <span>${g.cpu.toFixed(1)}%</span>
                            </div>`
                        ).join('');
                    } else {
                        list.innerHTML = '<div class="game-item"><span>无检测到</span><span>-</span></div>';
                    }
                    
                    document.getElementById('last-update').textContent = new Date().toLocaleTimeString();
                });
        }
        
        function doAction(action) {
            fetch('/api/widget/' + action, {method: 'POST'})
                .then(r => r.json())
                .then(data => {
                    if (data.success) {
                        updateStatus();
                    }
                });
        }
        
        setInterval(updateStatus, 2000);
        updateStatus();
    </script>
</body>
</html>
'''

@widget_bp.route('/widget')
def widget_page():
    """小组件页面"""
    return render_template_string(WIDGET_HTML)

@widget_bp.route('/api/widget/status')
def get_widget_status():
    """获取小组件状态"""
    cpu = psutil.cpu_percent(interval=0.1)
    memory = psutil.virtual_memory().percent
    
    # 获取当前游戏进程
    gaming_processes = []
    try:
        for proc in psutil.process_iter(['name', 'cpu_percent']):
            try:
                name = proc.name().lower()
                if any(x in name for x in ['game', 'steam', 'epic', 'gaming', 'riot', 'valorant', 'league', 'minecraft', 'genshin', 'arknights']):
                    gaming_processes.append({
                        'name': proc.name(),
                        'cpu': proc.cpu_percent()
                    })
            except:
                pass
    except:
        pass
    
    gaming_processes.sort(key=lambda x: x['cpu'], reverse=True)
    
    return jsonify({
        'cpu': cpu,
        'memory': memory,
        'gaming_processes': gaming_processes[:5],
        'last_update': datetime.now().isoformat(),
        'optimization_enabled': True
    })

@widget_bp.route('/api/widget/optimize', methods=['POST'])
def widget_optimize():
    """小组件快捷优化"""
    # 这里可以调用实际的优化逻辑
    return jsonify({'success': True, 'message': '优化已触发'})

@widget_bp.route('/api/widget/games', methods=['POST'])
def widget_show_games():
    """小组件显示游戏"""
    return jsonify({'success': True, 'message': '游戏列表已刷新'})

@widget_bp.route('/api/widget/restore', methods=['POST'])
def widget_restore():
    """小组件恢复默认"""
    return jsonify({'success': True, 'message': '已触发恢复'})

@widget_bp.route('/api/widget/quick-actions')
def get_quick_actions():
    """获取快捷操作"""
    return jsonify({
        'actions': [
            {'id': 'optimize', 'label': '立即优化', 'icon': '⚡'},
            {'id': 'games', 'label': '查看游戏', 'icon': '🎮'},
            {'id': 'restore', 'label': '恢复默认', 'icon': '↩️'}
        ]
    })
