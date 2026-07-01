import http.server
import socketserver
import json
import sqlite3
from datetime import datetime
from urllib.parse import urlparse, parse_qs

positive_words = [
    "开心", "快乐", "高兴", "幸福", "满意", "喜欢", "爱", "好", "棒", "赞", 
    "优秀", "美好", "愉快", "兴奋", "惊喜", "喜悦", "欣慰", "满足",
    "美满", "愉悦", "激昂", "振奋", "欢喜", "兴高采烈",
    "笑", "乐", "甜", "美", "妙", "酷", "爽", "精彩", "出色", "完美",
    "成功", "胜利", "成就", "进步", "成长", "健康", "平安", "顺利", "幸运",
    "感谢", "感恩", "感激", "温馨", "温暖", "热情", "友善", "友好", "亲切",
    "希望", "信心", "勇气", "力量", "坚强", "勇敢", "乐观", "积极", "阳光"
]

negative_words = [
    "难过", "伤心", "痛苦", "失望", "愤怒", "生气", "讨厌", "恨", "坏", "差",
    "糟", "烦", "焦虑", "恐惧", "担心", "悲伤", "忧郁", "沮丧", "失落", "绝望",
    "难受", "郁闷", "烦躁", "烦恼", "忧虑", "紧张", "不安", "恐慌",
    "恼火", "怨恨", "不满", "抱怨", "责备", "批评", "指责",
    "灰心", "无奈", "无助", "孤独", "寂寞", "空虚", "无聊",
    "害怕", "担忧", "发愁", "困惑", "迷茫", "纠结",
    "失败", "挫折", "困难", "麻烦", "问题", "错误", "糟糕", "遗憾", "可惜"
]

DATABASE = "emotion_analysis.db"

def init_db():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS analysis_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            emotion TEXT NOT NULL,
            confidence REAL NOT NULL,
            created_at TEXT NOT NULL,
            details TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

def analyze_emotion(text):
    text_lower = text
    
    pos_count = 0
    neg_count = 0
    matched_pos = []
    matched_neg = []
    
    for word in positive_words:
        if word in text_lower:
            pos_count += 1
            if len(matched_pos) < 5:
                matched_pos.append(word)
    
    for word in negative_words:
        if word in text_lower:
            neg_count += 1
            if len(matched_neg) < 5:
                matched_neg.append(word)
    
    negation_words = ["不", "没", "无", "非", "否", "别", "不要", "不能", "不会"]
    negation_count = sum(1 for word in negation_words if word in text_lower)
    
    if negation_count > 0:
        pos_count, neg_count = neg_count, pos_count
    
    total = pos_count + neg_count
    
    if total == 0:
        emotion = '中性'
        confidence = 0.5
    elif pos_count > neg_count:
        emotion = '正面'
        confidence = min(0.95, pos_count / total)
    else:
        emotion = '负面'
        confidence = min(0.95, neg_count / total)
    
    return {
        'emotion': emotion,
        'confidence': confidence,
        'details': {
            'positive_count': pos_count,
            'negative_count': neg_count,
            'matched_positive': matched_pos,
            'matched_negative': matched_neg,
            'negation_count': negation_count,
            'method': 'rule_based'
        }
    }

class EmotionHandler(http.server.BaseHTTPRequestHandler):
    def send_json_response(self, data, status_code=200):
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))
    
    def do_OPTIONS(self):
        self.send_json_response({}, 200)
    
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        
        if path == '/':
            self.send_json_response({"message": "情感分析API服务运行中"})
        elif path == '/records':
            params = parse_qs(parsed.query)
            limit = int(params.get('limit', [100])[0])
            
            conn = sqlite3.connect(DATABASE)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, text, emotion, confidence, created_at, details
                FROM analysis_records
                ORDER BY created_at DESC
                LIMIT ?
            """, (limit,))
            
            records = []
            for row in cursor.fetchall():
                records.append({
                    "id": row[0],
                    "text": row[1],
                    "emotion": row[2],
                    "confidence": row[3],
                    "created_at": row[4],
                    "details": json.loads(row[5])
                })
            
            conn.close()
            self.send_json_response({"records": records})
        elif path == '/statistics':
            conn = sqlite3.connect(DATABASE)
            cursor = conn.cursor()
            
            cursor.execute("SELECT COUNT(*) FROM analysis_records")
            total = cursor.fetchone()[0]
            
            cursor.execute("""
                SELECT emotion, COUNT(*) as count 
                FROM analysis_records 
                GROUP BY emotion
            """)
            emotion_counts = {row[0]: row[1] for row in cursor.fetchall()}
            
            cursor.execute("""
                SELECT created_at, emotion 
                FROM analysis_records 
                ORDER BY created_at DESC
                LIMIT 30
            """)
            trend_data = []
            for row in cursor.fetchall():
                trend_data.append({
                    "date": row[0],
                    "emotion": row[1]
                })
            
            conn.close()
            
            self.send_json_response({
                "total_records": total,
                "emotion_distribution": emotion_counts,
                "recent_trend": trend_data
            })
        else:
            self.send_json_response({"error": "Not found"}, 404)
    
    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        
        if path == '/analyze':
            content_length = int(self.headers['Content-Length'])
            body = self.rfile.read(content_length).decode('utf-8')
            
            try:
                data = json.loads(body)
                text = data.get('text', '').strip()
                
                if not text:
                    self.send_json_response({"error": "文本内容不能为空"}, 400)
                    return
                
                result = analyze_emotion(text)
                
                conn = sqlite3.connect(DATABASE)
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO analysis_records (text, emotion, confidence, created_at, details)
                    VALUES (?, ?, ?, ?, ?)
                """, (text, result['emotion'], result['confidence'], 
                      datetime.now().isoformat(), json.dumps(result['details'])))
                conn.commit()
                conn.close()
                
                self.send_json_response(result)
            except json.JSONDecodeError:
                self.send_json_response({"error": "Invalid JSON"}, 400)
        else:
            self.send_json_response({"error": "Not found"}, 404)
    
    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = parsed.path
        
        if path.startswith('/records/'):
            try:
                record_id = int(path.split('/')[-1])
                
                conn = sqlite3.connect(DATABASE)
                cursor = conn.cursor()
                cursor.execute("DELETE FROM analysis_records WHERE id = ?", (record_id,))
                conn.commit()
                rows_deleted = cursor.rowcount
                conn.close()
                
                if rows_deleted == 0:
                    self.send_json_response({"error": "记录不存在"}, 404)
                else:
                    self.send_json_response({"message": "删除成功"})
            except ValueError:
                self.send_json_response({"error": "Invalid ID"}, 400)
        else:
            self.send_json_response({"error": "Not found"}, 404)

if __name__ == "__main__":
    PORT = 8000
    with socketserver.TCPServer(("", PORT), EmotionHandler) as httpd:
        print(f"情感分析API服务运行在 http://localhost:{PORT}")
        httpd.serve_forever()