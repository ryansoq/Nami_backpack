extends Node

# 測試腳本 - 驗證 Godot 專案是否正常工作

func _ready():
	print("=== KAS 三國 MVP 測試 ===")
	print("Godot 版本: ", Engine.get_version_info())
	print("專案名稱: ", ProjectSettings.get_setting("application/config/name"))
	
	# 測試 GameManager
	if GameManager:
		print("✅ GameManager 已載入")
		print("玩家 tKAS: ", GameManager.player_data.tkas)
		print("城池數量: ", GameManager.cities.size())
		
		# 測試城池資料
		var runan_city = GameManager.get_city_data("City_RuNan")
		if not runan_city.is_empty():
			print("✅ 城池資料正確 - 汝南:", runan_city.name)
		
		# 測試兵種資料
		print("兵種數量: ", GameManager.troop_stats.size())
		print("步兵費用: ", GameManager.troop_stats.infantry.cost)
		
		print("=== 測試完成 ===")
	else:
		print("❌ GameManager 未載入")

func test_battle():
	# 測試戰鬥系統
	print("\n=== 測試戰鬥系統 ===")
	var attacking_troops = {"infantry": 100, "cavalry": 50}
	var result = GameManager._calculate_battle("City_WanCheng", attacking_troops)
	print("戰鬥結果: ", result)