import os
import json

from math import floor
from random import randint
from time import sleep
from bs4 import BeautifulSoup
from urllib.request import Request, urlopen

RESCRAPE_ELECTION_HTML = False

def scrape_table(url):

    election_url = 'https://vote.nyc' + url.a['href'].replace(' ', '%20')
    
    if RESCRAPE_ELECTION_HTML:
        req = Request(election_url , headers={'User-Agent': 'Mozilla/5.0'})
        webpage = urlopen(req).read()
        
        # save html
        with open('election_html/' + election_url.split('/')[-1], 'wb') as election_html_file:
            election_html_file.write(webpage)
            
    else:
        with open('election_html/' + election_url.split('/')[-1], 'rb') as election_html_file:
            webpage = election_html_file.read()

    # scrape html
    election_soup = BeautifulSoup(webpage, 'html.parser')
    
    # get contest name and date
    contest_name = None
    contest_date = None
    name_next = False
    date_next = False
    for td in election_soup.find_all('td'):
        
        # name
        if name_next:
            contest_name = td.contents[0]
            name_next = False
        if td.contents and td.contents[0] == 'Contest:':
            name_next = True
        
        # date
        if date_next:
            contest_date = td.contents[0]
            date_next = False
        if td.contents and td.contents[0] == 'Election Date:':
            date_next = True
                
    #print('scraping: ' + contest_name + ' ' + contest_date)        

    # loop through table
    table_root = election_soup.select('html > body > form > div > div > table > tr > td > table > tr:nth-child(4) > td > table > tr:nth-child(4) > td > table')[0]
    
    # look at top rows first
    # record round nums
    round_nums = [i.contents[0] for i in table_root.select('tr')[1].select('td')[1:]]
    
    # record eliminations
    eliminateds = {
        round_num: elim.contents[0].strip() for round_num, elim 
        in zip(round_nums, table_root.select('tr')[2].select('td')[2:] + [''])
        if elim and elim.contents and elim.contents[0].strip()
        }
    
    # record winners
    electeds = {
        round_num: elec.contents[0].strip() for round_num, elec 
        in zip(round_nums, table_root.select('tr')[3].select('td')[1:])
        if elec.contents and elec.contents[0].strip()
        }
    
    # then loop through candidate rows
    candidate_rounds = {}
    for candidate_tr in table_root.select('tr')[5:]:
        
        candidate_tds = candidate_tr.select('td')
        
        candidate_name = candidate_tds[0].contents[0].strip()
        candidate_rounds[candidate_name] = {}
        
        for round_idx, candidate_td in enumerate(candidate_tr.select('td')[1:]):
            
            # empty cell
            if not candidate_td.contents:
                continue
            
            # eliminated candidate
            if candidate_td.contents[0] == "-XXX":
                continue
            
            # remove punctuation
            val_string = candidate_td.contents[0].strip().strip('%').replace(',', '')
            
            # non-empty empty cell '\xa0'
            if not val_string:
                continue
            
            col_round_num = round_nums[floor(round_idx/3)]
            if col_round_num not in candidate_rounds[candidate_name]:
                candidate_rounds[candidate_name][col_round_num] = {}
            
            if round_idx % 3 == 0:
                candidate_rounds[candidate_name][col_round_num]['count'] = int(val_string)
                continue
            if round_idx % 3 == 1:
                candidate_rounds[candidate_name][col_round_num]['percent'] = float(val_string)
                continue
            if round_idx % 3 == 2:
                candidate_rounds[candidate_name][col_round_num]['transfer_received'] = int(val_string)
                continue
            
    # shift rounds if extra round column in present due to early winner
    if any(k for k, v in electeds.items() if ' over 50%' in v):
        
        new_round_nums = []
        new_eliminateds = {}
        new_electeds = {}
        new_candidate_rounds = {candidate: {} for candidate in candidate_rounds.keys()}
        
        new_round_int = 1
        for round_num in round_nums:
            
            new_round_num = f'Round {new_round_int}'
            
            if round_num in electeds and ' over 50%' in electeds[round_num]:
                prev_round_num = f'Round {new_round_int-1}'
                new_electeds[prev_round_num] = electeds[round_num].split(' over 50%')[0]
                if round_num in eliminateds:
                    new_eliminateds[prev_round_num] = eliminateds[round_num]
                for candidate in candidate_rounds.keys():
                    if round_num in candidate_rounds[candidate]:
                        new_candidate_rounds[candidate][prev_round_num] = candidate_rounds[candidate][round_num]
                continue

            new_round_nums.append(new_round_num)
            if round_num in electeds:
                new_electeds[new_round_num] = electeds[round_num]
            if round_num in eliminateds:
                new_eliminateds[new_round_num] = eliminateds[round_num]
            for candidate in candidate_rounds.keys():
                if round_num in candidate_rounds[candidate]:
                    new_candidate_rounds[candidate][new_round_num] = candidate_rounds[candidate][round_num]
            new_round_int += 1
                        
        round_nums = new_round_nums
        electeds = new_electeds
        eliminateds = new_eliminateds
        candidate_rounds = new_candidate_rounds

    # make tabulator json dict for output
    tabulator_json = {'results': [], 'config': []}
    
    prev_elec = []
    prev_elim = []
    elec_round = None
    for round_num_idx, round_num in enumerate(round_nums):
        
        tally_dict = {
            candidate: candidate_rounds[round_num]['count'] for
            candidate, candidate_rounds in candidate_rounds.items()
            if round_num in candidate_rounds and 'count' in candidate_rounds[round_num]
        }
        
        if 'Inactive ballots' not in tally_dict:
            tally_dict['Inactive ballots'] = 0
        
        round_elim = [i.strip() for i in eliminateds[round_num].split(';')] if round_num in eliminateds else None
        round_elim = round_elim if round_elim not in prev_elim else None
        prev_elim.append(round_elim)

        round_elec = [i.strip() for i in electeds[round_num].split(';')] if round_num in electeds else None
        round_elec = round_elec if round_elec not in prev_elec else None
        if round_elec:
            elec_round = round_num_idx
        prev_elec.append(round_elec)
        
        round_transfer = {
            candidate: candidate_rounds[round_num]['transfer_received'] for 
            candidate, candidate_rounds in candidate_rounds.items()
            if round_num in candidate_rounds and 'transfer_received' in candidate_rounds[round_num]
        }
        
        if round_elec and len(round_elec) > 1:
            raise RuntimeError
        
        tallyResults_ld = []
        if round_elec:
            tallyResults_ld.append({'elected': round_elec[0]})
        if round_elim and len(round_elim) == 1:
            tallyResults_ld.append({
                'eliminated': round_elim[0],
                'transfers': round_transfer
                })
        if round_elim and len(round_elim) > 1:
            for elim_candidate in round_elim:
                tallyResults_ld.append({'eliminated': elim_candidate, 'transfers': {}})

        
        tabulator_json['results'].append({
            'round': int(round_num.strip('Round ')),
            'tally': tally_dict,
            'tallyResults': tallyResults_ld
        })
        
    tabulator_json['config'] = {
        'contest': contest_name,
        'date': contest_date,
        'jurisdiction': 'New York City',
        'threshold': sum(count for candidate, count 
                         in tabulator_json['results'][elec_round]['tally'].items() 
                         if candidate != "Inactive ballots")/2
    }

    outfile_name = "election_json/" + contest_name + ' ' + contest_date.replace('/', '') + ".json"
    with open(outfile_name, "w") as outfile: 
        json.dump(tabulator_json, outfile)
                
if __name__ == '__main__':
        
    if not os.path.isdir('election_html'):
        os.mkdir('election_html')
        
    if not os.path.isdir('election_json'):
        os.mkdir('election_json')
               
    # scrape link list page
    with open("link_list_page.html", encoding='utf8') as fp:
        
        soup = BeautifulSoup(fp, 'html.parser')
        
        tbl = soup.find_all('table')[0]
        for tr in tbl.find_all('tr'):
            tds = [td for td in tr.find_all('td')]
            if tds:
                if RESCRAPE_ELECTION_HTML:    
                    # random pause
                    sleep(randint(1, 5))
                scrape_table(tds[2])
