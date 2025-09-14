import argparse, csv, json, pathlib, re, time
import requests
from bs4 import BeautifulSoup

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "datasets" / "legendaryCreatures.csv"
url = "https://moxfield.com/decks/L8WYfRSyekSuuqU1I68NJw" # webpage with all legendary creatures
creature_list = []

def get_leg_creatures():
   response = requests.get(url)
   print(response)

   if response.status_code == 200:
    soup = BeautifulSoup(response.content, 'html.parser')
    print(soup)

    legendaryCreatures = soup.find_all('div', class_='w-100')
    print(legendaryCreatures)

    for creature in legendaryCreatures:
        name = creature.find('span', class_='underline').text
        creature_list.append(name)

    print(creature_list)


get_leg_creatures()



