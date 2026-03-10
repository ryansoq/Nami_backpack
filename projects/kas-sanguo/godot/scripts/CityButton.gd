extends Button

var city_id: String

func _ready():
	city_id = name
	
	# 設定城池按鈕樣式
	custom_minimum_size = Vector2(60, 60)
	
	# 根據城池資料設定顏色
	_update_appearance()
	
	# 連接 GameManager 訊號來更新外觀
	if GameManager.city_captured.is_connected(_on_city_captured):
		GameManager.city_captured.disconnect(_on_city_captured)
	GameManager.city_captured.connect(_on_city_captured)

func _update_appearance():
	var city_data = GameManager.get_city_data(city_id)
	if city_data.is_empty():
		return
	
	# 根據擁有者設定顏色
	match city_data.owner:
		"player":
			modulate = Color(0.392, 0.584, 1, 1) # 藍色
		"npc": 
			modulate = Color(0.5, 0.5, 0.5, 1) # 灰色
		_:
			modulate = Color(1, 0.2, 0.2, 1) # 紅色（敵人）

func _on_city_captured(captured_city_id: String, new_owner: String):
	if captured_city_id == city_id:
		_update_appearance()