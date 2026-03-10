extends Control

@onready var player_name_label = $PlayerName
@onready var tkas_label = $tKAS 
@onready var cities_label = $Cities
@onready var army_label = $Army

func _ready():
	update_display()

func update_display():
	var player_data = GameManager.player_data
	
	player_name_label.text = player_data.name
	tkas_label.text = "tKAS: " + str(player_data.tkas)
	cities_label.text = "城池: " + str(player_data.cities_owned)
	army_label.text = "兵力: " + str(player_data.total_army)