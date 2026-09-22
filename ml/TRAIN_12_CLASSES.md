"""Рекомендуемый порядок классов при дообучении до 12 (как data/train_12).

names:
  0: excavator
  1: bulldozer
  2: loader
  3: dump_truck
  4: concrete_mixer
  5: concrete_pump
  6: tower_crane
  7: autocrane
  8: pile_driver
  9: roller
  10: crane_manipulator
  11: truck

Инференс мапит в первую очередь по имени класса модели.
После обучения положите best.pt в ml/weights/best.pt
"""
