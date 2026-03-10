extends Node

# 遊戲資料
var player_data = {
	"name": "玩家",
	"tkas": 100,
	"cities_owned": 1,
	"total_army": 50
}

# 城池資料
var cities = {
	"City_LuoYang": {
		"name": "洛陽",
		"tier": "S",
		"production": 100,
		"owner": "npc",
		"garrison": {"infantry": 500, "cavalry": 0},
		"defense_level": 3,
		"position": Vector2(400, 300)
	},
	"City_XuChang": {
		"name": "許昌", 
		"tier": "A",
		"production": 60,
		"owner": "npc",
		"garrison": {"infantry": 300, "cavalry": 100},
		"defense_level": 2,
		"position": Vector2(450, 350)
	},
	"City_XiangYang": {
		"name": "襄陽",
		"tier": "B", 
		"production": 30,
		"owner": "npc",
		"garrison": {"infantry": 200, "cavalry": 0},
		"defense_level": 2,
		"position": Vector2(430, 420)
	},
	"City_HanZhong": {
		"name": "漢中",
		"tier": "B",
		"production": 30,
		"owner": "npc", 
		"garrison": {"infantry": 200, "cavalry": 0},
		"defense_level": 2,
		"position": Vector2(250, 380)
	},
	"City_RuNan": {
		"name": "汝南",
		"tier": "C",
		"production": 15,
		"owner": "player",
		"garrison": {"infantry": 50, "cavalry": 0},
		"defense_level": 1,
		"position": Vector2(480, 400)
	},
	"City_WanCheng": {
		"name": "宛城",
		"tier": "C",
		"production": 15,
		"owner": "npc",
		"garrison": {"infantry": 100, "cavalry": 0}, 
		"defense_level": 1,
		"position": Vector2(370, 380)
	},
	"City_ChenLiu": {
		"name": "陳留",
		"tier": "D",
		"production": 5,
		"owner": "npc",
		"garrison": {"infantry": 30, "cavalry": 0},
		"defense_level": 1,
		"position": Vector2(450, 220)
	},
	"City_XiaoPei": {
		"name": "小沛", 
		"tier": "D",
		"production": 5,
		"owner": "npc",
		"garrison": {"infantry": 30, "cavalry": 0},
		"defense_level": 1,
		"position": Vector2(550, 250)
	},
	"City_XinYe": {
		"name": "新野",
		"tier": "D",
		"production": 5,
		"owner": "npc",
		"garrison": {"infantry": 20, "cavalry": 0},
		"defense_level": 1,
		"position": Vector2(450, 480)
	},
	"City_ShangYong": {
		"name": "上庸",
		"tier": "D", 
		"production": 5,
		"owner": "npc",
		"garrison": {"infantry": 20, "cavalry": 0},
		"defense_level": 1,
		"position": Vector2(320, 450)
	}
}

# 兵種設定
var troop_stats = {
	"infantry": {
		"name": "步兵",
		"attack": 5,
		"defense": 6,
		"speed": 1.0,
		"cost": 1.5,
		"train_time": 15, # 分鐘
	},
	"cavalry": {
		"name": "騎兵",
		"attack": 8,
		"defense": 3, 
		"speed": 1.5,
		"cost": 3.0,
		"train_time": 30,
	}
}

# 行軍資料
var active_marches = []

# 城池連接（鄰接列表）
var city_connections = {
	"City_LuoYang": ["City_XuChang", "City_WanCheng", "City_ChenLiu"],
	"City_XuChang": ["City_LuoYang", "City_RuNan", "City_ChenLiu"],
	"City_XiangYang": ["City_WanCheng", "City_RuNan", "City_XinYe"],
	"City_HanZhong": ["City_WanCheng", "City_ShangYong"],
	"City_RuNan": ["City_XuChang", "City_XiangYang", "City_WanCheng"],
	"City_WanCheng": ["City_LuoYang", "City_XiangYang", "City_HanZhong", "City_RuNan"],
	"City_ChenLiu": ["City_LuoYang", "City_XuChang", "City_XiaoPei"],
	"City_XiaoPei": ["City_ChenLiu"],
	"City_XinYe": ["City_XiangYang", "City_ShangYong"],
	"City_ShangYong": ["City_HanZhong", "City_XinYe"]
}

# 訊號
signal city_captured(city_id: String, new_owner: String)
signal march_started(march_data: Dictionary)
signal march_arrived(march_data: Dictionary)
signal tkas_changed(new_amount: int)

func _ready():
	# 每分鐘檢查城池產出
	var timer = Timer.new()
	timer.wait_time = 60.0 # 60 秒
	timer.timeout.connect(_update_production)
	timer.autostart = true
	add_child(timer)
	
	# 每秒檢查行軍狀態
	var march_timer = Timer.new()
	march_timer.wait_time = 1.0
	march_timer.timeout.connect(_update_marches)
	march_timer.autostart = true
	add_child(march_timer)

func _update_production():
	# 計算玩家城池的 tKAS 產出
	var total_production = 0
	for city_id in cities:
		var city = cities[city_id]
		if city.owner == "player":
			total_production += city.production
	
	if total_production > 0:
		# MVP 版本：每分鐘產出，而不是每小時
		var production_per_minute = total_production / 60.0
		player_data.tkas += int(production_per_minute)
		tkas_changed.emit(player_data.tkas)
		print("城池產出: +", int(production_per_minute), " tKAS")

func _update_marches():
	# 檢查進行中的行軍
	var current_time = Time.get_unix_time_from_system()
	var completed_marches = []
	
	for i in range(active_marches.size()):
		var march = active_marches[i]
		if current_time >= march.arrive_time:
			completed_marches.append(i)
			_handle_march_arrival(march)
	
	# 移除已完成的行軍（從後往前移除避免索引問題）
	for i in range(completed_marches.size() - 1, -1, -1):
		active_marches.remove_at(completed_marches[i])

func _handle_march_arrival(march: Dictionary):
	print("行軍抵達: ", cities[march.target].name)
	march_arrived.emit(march)
	
	# 戰鬥計算
	var result = _calculate_battle(march.target, march.troops)
	_show_battle_result(march, result)

func _calculate_battle(target_city_id: String, attacking_troops: Dictionary) -> Dictionary:
	var city = cities[target_city_id]
	var defender_troops = city.garrison
	
	# 簡化戰鬥計算
	var attacker_power = 0
	var defender_power = 0
	
	# 計算攻方戰鬥力
	for troop_type in attacking_troops:
		var count = attacking_troops[troop_type]
		var stats = troop_stats[troop_type]
		attacker_power += count * stats.attack
	
	# 計算守方戰鬥力（含城防加成）
	for troop_type in defender_troops:
		var count = defender_troops[troop_type]
		if count > 0:
			var stats = troop_stats[troop_type]
			defender_power += count * stats.defense
	
	# 城防加成
	defender_power *= (1.0 + city.defense_level * 0.1)
	
	print("戰鬥力對比 - 攻方: ", attacker_power, " 守方: ", defender_power)
	
	var result = {
		"attacker_wins": attacker_power > defender_power,
		"attacker_power": attacker_power,
		"defender_power": defender_power,
		"target_city": target_city_id
	}
	
	if result.attacker_wins:
		# 攻方勝利，佔領城池
		city.owner = "player"
		city.garrison = attacking_troops.duplicate()
		player_data.cities_owned += 1
		city_captured.emit(target_city_id, "player")
		
		# 戰利品
		var loot = city.production * 2 # 獲得 2 小時的產出
		player_data.tkas += loot
		tkas_changed.emit(player_data.tkas)
		print("佔領 ", city.name, "！獲得 ", loot, " tKAS")
	else:
		# 攻方敗北，部隊損失
		print("攻城失敗！")
	
	return result

func _show_battle_result(march: Dictionary, result: Dictionary):
	# 這裡可以顯示戰報面板，MVP 版本先用 print
	if result.attacker_wins:
		print("✅ 勝利！佔領了 ", cities[result.target_city].name)
	else:
		print("❌ 敗北！攻城失敗")

func start_march(from_city: String, to_city: String, troops: Dictionary) -> bool:
	# 檢查是否有足夠兵力
	var city = cities[from_city]
	if city.owner != "player":
		return false
	
	for troop_type in troops:
		var required = troops[troop_type]
		if city.garrison[troop_type] < required:
			print("兵力不足: ", troop_type)
			return false
	
	# 計算行軍時間和消耗
	var march_time = _calculate_march_time(from_city, to_city, troops)
	var supply_cost = _calculate_supply_cost(troops, march_time)
	
	if player_data.tkas < supply_cost:
		print("tKAS 不足，需要 ", supply_cost, " tKAS")
		return false
	
	# 扣除兵力和 tKAS
	for troop_type in troops:
		city.garrison[troop_type] -= troops[troop_type]
	player_data.tkas -= supply_cost
	tkas_changed.emit(player_data.tkas)
	
	# 建立行軍記錄
	var march_data = {
		"id": "march_" + str(Time.get_unix_time_from_system()),
		"origin": from_city,
		"target": to_city,
		"troops": troops,
		"start_time": Time.get_unix_time_from_system(),
		"arrive_time": Time.get_unix_time_from_system() + march_time,
		"march_time": march_time,
		"supply_cost": supply_cost
	}
	
	active_marches.append(march_data)
	march_started.emit(march_data)
	
	print("開始行軍: ", cities[from_city].name, " → ", cities[to_city].name)
	print("預計 ", march_time / 60.0, " 分鐘後抵達")
	
	return true

func _calculate_march_time(from: String, to: String, troops: Dictionary) -> float:
	# MVP 版本：簡化距離計算
	var base_time = 1800.0 # 30 分鐘基礎時間
	
	# 根據兵種調整速度（取最慢的）
	var slowest_speed = 999.0
	for troop_type in troops:
		if troops[troop_type] > 0:
			slowest_speed = min(slowest_speed, troop_stats[troop_type].speed)
	
	if slowest_speed == 999.0:
		slowest_speed = 1.0
	
	return base_time / slowest_speed

func _calculate_supply_cost(troops: Dictionary, march_time: float) -> int:
	# 計算糧草消耗
	var total_troops = 0
	for troop_type in troops:
		total_troops += troops[troop_type]
	
	var cost = total_troops * (march_time / 3600.0) * 0.1
	return max(1, int(cost))

func train_troops(city_id: String, troop_type: String, amount: int) -> bool:
	var city = cities[city_id]
	if city.owner != "player":
		return false
	
	var total_cost = troop_stats[troop_type].cost * amount
	if player_data.tkas < total_cost:
		print("tKAS 不足，需要 ", total_cost, " tKAS")
		return false
	
	# MVP 版本：即時訓練完成
	player_data.tkas -= int(total_cost)
	city.garrison[troop_type] += amount
	tkas_changed.emit(player_data.tkas)
	
	# 更新總兵力
	_update_total_army()
	
	print("訓練完成: ", amount, " ", troop_stats[troop_type].name)
	return true

func upgrade_defense(city_id: String) -> bool:
	var city = cities[city_id]
	if city.owner != "player":
		return false
	
	var current_level = city.defense_level
	var upgrade_cost = 10 * (current_level + 1)
	
	if player_data.tkas < upgrade_cost:
		print("tKAS 不足，需要 ", upgrade_cost, " tKAS")
		return false
	
	if current_level >= 10:
		print("城防已達最高等級")
		return false
	
	player_data.tkas -= upgrade_cost
	city.defense_level += 1
	tkas_changed.emit(player_data.tkas)
	
	print("城防升級至等級 ", city.defense_level)
	return true

func _update_total_army():
	# 計算玩家總兵力
	var total = 0
	for city_id in cities:
		var city = cities[city_id]
		if city.owner == "player":
			for troop_type in city.garrison:
				total += city.garrison[troop_type]
	
	player_data.total_army = total

func get_city_data(city_id: String) -> Dictionary:
	return cities.get(city_id, {})

func get_player_cities() -> Array:
	var player_cities = []
	for city_id in cities:
		if cities[city_id].owner == "player":
			player_cities.append(city_id)
	return player_cities

func is_cities_connected(city_a: String, city_b: String) -> bool:
	# 檢查兩座城池是否相連
	if city_a in city_connections and city_b in city_connections[city_a]:
		return true
	return false

func get_connected_cities(city_id: String) -> Array:
	return city_connections.get(city_id, [])