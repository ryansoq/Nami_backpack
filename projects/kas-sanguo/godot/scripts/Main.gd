extends Control

@onready var hud = $HUD
@onready var city_panel = $CityPanel
@onready var march_panel = $MarchPanel

# 城池面板元素
@onready var city_title = $CityPanel/Panel/VBoxContainer/Title
@onready var city_owner = $CityPanel/Panel/VBoxContainer/Info/Owner
@onready var city_garrison = $CityPanel/Panel/VBoxContainer/Info/Garrison
@onready var city_production = $CityPanel/Panel/VBoxContainer/Info/Production
@onready var city_defense = $CityPanel/Panel/VBoxContainer/Info/Defense

# 出兵面板元素
@onready var from_city_label = $MarchPanel/Panel/VBoxContainer/FromCity
@onready var infantry_spinbox = $MarchPanel/Panel/VBoxContainer/TroopSelection/InfantryContainer/InfantrySpinBox
@onready var cavalry_spinbox = $MarchPanel/Panel/VBoxContainer/TroopSelection/CavalryContainer/CavalrySpinBox
@onready var target_dropdown = $MarchPanel/Panel/VBoxContainer/TargetSelection/TargetDropdown
@onready var march_time_label = $MarchPanel/Panel/VBoxContainer/MarchInfo/MarchTime
@onready var supply_cost_label = $MarchPanel/Panel/VBoxContainer/MarchInfo/SupplyCost

# 當前選中的城池
var selected_city_id = ""
var march_source_city = ""

# 縮放
var current_zoom = 1.0
var zoom_min = 0.5
var zoom_max = 2.5
var zoom_step = 0.25
@onready var map_view = $MapContainer/MapView

func _ready():
	# 連接 GameManager 訊號
	GameManager.city_captured.connect(_on_city_captured)
	GameManager.march_started.connect(_on_march_started)
	GameManager.march_arrived.connect(_on_march_arrived)
	GameManager.tkas_changed.connect(_on_tkas_changed)
	
	# 初始化 HUD
	_update_hud()
	
	# 初始化城池顏色
	_update_city_colors()
	
	# 連接城池按鈕
	_connect_city_buttons()

func _connect_city_buttons():
	# 連接所有城池按鈕的點擊事件
	var cities_container = $MapContainer/MapView/Cities
	for child in cities_container.get_children():
		if child is Button:
			child.pressed.connect(_on_city_button_pressed.bind(child.name))

func _update_hud():
	var hud_script = hud.get_script()
	if hud_script and hud.has_method("update_display"):
		hud.update_display()

func _update_city_colors():
	var cities_container = $MapContainer/MapView/Cities
	for child in cities_container.get_children():
		if child is Button:
			var city_id = child.name
			var city_data = GameManager.get_city_data(city_id)
			
			if city_data.owner == "player":
				child.modulate = Color(0.392, 0.584, 1, 1) # 藍色
			elif city_data.owner == "npc":
				child.modulate = Color(0.5, 0.5, 0.5, 1) # 灰色
			else:
				child.modulate = Color(1, 0.2, 0.2, 1) # 紅色（敵人）

func _on_city_button_pressed(city_id: String):
	selected_city_id = city_id
	_show_city_panel(city_id)

func _show_city_panel(city_id: String):
	var city_data = GameManager.get_city_data(city_id)
	if city_data.is_empty():
		return
	
	# 更新城池面板資訊
	city_title.text = city_data.name + " (" + city_data.tier + "級)"
	
	var owner_text = "擁有者: "
	if city_data.owner == "player":
		owner_text += "你"
	elif city_data.owner == "npc":
		owner_text += "NPC"
	else:
		owner_text += "敵人"
	city_owner.text = owner_text
	
	# 駐軍資訊
	var garrison_text = "駐軍: "
	var garrison_parts = []
	for troop_type in city_data.garrison:
		var count = city_data.garrison[troop_type]
		if count > 0:
			var troop_name = GameManager.troop_stats[troop_type].name
			garrison_parts.append(troop_name + " " + str(count))
	
	if garrison_parts.is_empty():
		garrison_text += "無"
	else:
		garrison_text += " ".join(garrison_parts)
	city_garrison.text = garrison_text
	
	city_production.text = "產出: " + str(city_data.production) + " tKAS/時"
	city_defense.text = "城防: 等級 " + str(city_data.defense_level)
	
	# 根據城池擁有者顯示/隱藏按鈕
	var actions_container = $CityPanel/Panel/VBoxContainer/Actions
	var train_button = actions_container.get_node("TrainTroops")
	var upgrade_button = actions_container.get_node("UpgradeDefense")
	var march_button = actions_container.get_node("SendArmy")
	
	var is_player_city = city_data.owner == "player"
	train_button.visible = is_player_city
	upgrade_button.visible = is_player_city
	march_button.visible = is_player_city
	
	city_panel.visible = true

func _on_close_city_panel():
	city_panel.visible = false
	selected_city_id = ""

func _on_train_troops_pressed():
	# 簡單的訓練面板（MVP 版本）
	var city_data = GameManager.get_city_data(selected_city_id)
	if city_data.is_empty() or city_data.owner != "player":
		return
	
	# 建立簡單的輸入對話框
	_show_train_dialog()

func _show_train_dialog():
	# MVP 版本：使用簡單的確認對話框
	var dialog = AcceptDialog.new()
	dialog.title = "訓練部隊"
	
	var vbox = VBoxContainer.new()
	
	# 步兵訓練
	var infantry_container = HBoxContainer.new()
	var infantry_label = Label.new()
	infantry_label.text = "步兵 (1.5 tKAS/個):"
	var infantry_spinbox = SpinBox.new()
	infantry_spinbox.max_value = 100
	infantry_spinbox.value = 10
	infantry_container.add_child(infantry_label)
	infantry_container.add_child(infantry_spinbox)
	vbox.add_child(infantry_container)
	
	# 騎兵訓練
	var cavalry_container = HBoxContainer.new()
	var cavalry_label = Label.new()
	cavalry_label.text = "騎兵 (3 tKAS/個):"
	var cavalry_spinbox = SpinBox.new()
	cavalry_spinbox.max_value = 100
	cavalry_spinbox.value = 5
	cavalry_container.add_child(cavalry_label)
	cavalry_container.add_child(cavalry_spinbox)
	vbox.add_child(cavalry_container)
	
	dialog.add_child(vbox)
	add_child(dialog)
	
	dialog.confirmed.connect(func():
		var infantry_count = int(infantry_spinbox.value)
		var cavalry_count = int(cavalry_spinbox.value)
		
		if infantry_count > 0:
			GameManager.train_troops(selected_city_id, "infantry", infantry_count)
		if cavalry_count > 0:
			GameManager.train_troops(selected_city_id, "cavalry", cavalry_count)
		
		# 更新顯示
		_show_city_panel(selected_city_id)
		_update_hud()
		dialog.queue_free()
	)
	
	dialog.popup_centered()

func _on_upgrade_defense_pressed():
	if GameManager.upgrade_defense(selected_city_id):
		_show_city_panel(selected_city_id)
		_update_hud()

func _on_send_army_pressed():
	march_source_city = selected_city_id
	_show_march_panel()

func _show_march_panel():
	var city_data = GameManager.get_city_data(march_source_city)
	if city_data.is_empty():
		return
	
	from_city_label.text = "從: " + city_data.name
	
	# 設定可用兵力
	infantry_spinbox.max_value = city_data.garrison.infantry
	cavalry_spinbox.max_value = city_data.garrison.cavalry
	infantry_spinbox.value = 0
	cavalry_spinbox.value = 0
	
	# 設定目標城池下拉選單
	target_dropdown.clear()
	var connected_cities = GameManager.get_connected_cities(march_source_city)
	for target_city_id in connected_cities:
		var target_data = GameManager.get_city_data(target_city_id)
		if not target_data.is_empty():
			target_dropdown.add_item(target_data.name, target_dropdown.get_item_count())
			target_dropdown.set_item_metadata(target_dropdown.get_item_count() - 1, target_city_id)
	
	# 連接數值變更事件來更新行軍資訊
	if not infantry_spinbox.value_changed.is_connected(_update_march_info):
		infantry_spinbox.value_changed.connect(_update_march_info)
		cavalry_spinbox.value_changed.connect(_update_march_info)
		target_dropdown.item_selected.connect(_update_march_info)
	
	_update_march_info()
	
	march_panel.visible = true

func _update_march_info(value = null):
	if target_dropdown.selected == -1:
		return
	
	var target_city_id = target_dropdown.get_item_metadata(target_dropdown.selected)
	var troops = {
		"infantry": int(infantry_spinbox.value),
		"cavalry": int(cavalry_spinbox.value)
	}
	
	# 計算行軍時間（簡化版本）
	var march_time = GameManager._calculate_march_time(march_source_city, target_city_id, troops)
	march_time_label.text = "行軍時間: " + str(int(march_time / 60)) + " 分鐘"
	
	# 計算補給消耗
	var supply_cost = GameManager._calculate_supply_cost(troops, march_time)
	supply_cost_label.text = "糧草消耗: " + str(supply_cost) + " tKAS"

func _on_confirm_march():
	if target_dropdown.selected == -1:
		print("請選擇目標城池")
		return
	
	var target_city_id = target_dropdown.get_item_metadata(target_dropdown.selected)
	var troops = {
		"infantry": int(infantry_spinbox.value),
		"cavalry": int(cavalry_spinbox.value)
	}
	
	# 檢查是否有選擇部隊
	if troops.infantry + troops.cavalry == 0:
		print("請選擇要出征的部隊")
		return
	
	if GameManager.start_march(march_source_city, target_city_id, troops):
		march_panel.visible = false
		city_panel.visible = false
		_update_hud()
		print("出兵成功！")
	else:
		print("出兵失敗！")

func _on_cancel_march():
	march_panel.visible = false

func _on_city_captured(city_id: String, new_owner: String):
	print("城池易主: ", GameManager.get_city_data(city_id).name, " -> ", new_owner)
	_update_city_colors()
	_update_hud()

func _on_march_started(march_data: Dictionary):
	print("開始行軍: ", march_data.origin, " → ", march_data.target)
	# 這裡可以添加行軍箭頭動畫
	_show_march_arrow(march_data)

func _on_march_arrived(march_data: Dictionary):
	print("行軍抵達: ", march_data.target)
	# 移除行軍箭頭
	_remove_march_arrow(march_data.id)

func _show_march_arrow(march_data: Dictionary):
	# MVP 版本：簡單的行軍指示
	var armies_container = $MapContainer/MapView/Armies
	
	var arrow = Label.new()
	arrow.name = "March_" + march_data.id
	arrow.text = "⚔️"
	arrow.add_theme_font_size_override("font_size", 20)
	
	# 計算起點和終點位置
	var origin_pos = GameManager.cities[march_data.origin].position
	var target_pos = GameManager.cities[march_data.target].position
	
	# 設定箭頭初始位置
	arrow.position = origin_pos - Vector2(10, 10)
	armies_container.add_child(arrow)
	
	# 建立移動動畫
	var tween = create_tween()
	var duration = march_data.arrive_time - march_data.start_time
	tween.tween_property(arrow, "position", target_pos - Vector2(10, 10), duration)

func _remove_march_arrow(march_id: String):
	var armies_container = $MapContainer/MapView/Armies
	var arrow = armies_container.get_node_or_null("March_" + march_id)
	if arrow:
		arrow.queue_free()

func _on_tkas_changed(new_amount: int):
	_update_hud()

# === 縮放功能 ===
func _on_zoom_in():
	current_zoom = min(current_zoom + zoom_step, zoom_max)
	_apply_zoom()

func _on_zoom_out():
	current_zoom = max(current_zoom - zoom_step, zoom_min)
	_apply_zoom()

func _apply_zoom():
	map_view.scale = Vector2(current_zoom, current_zoom)