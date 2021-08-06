
import json
import os
import pathlib
import hashlib

import pandas as pd

dir_path = pathlib.Path(os.path.dirname(os.path.realpath(__file__)))

scraped_dir = dir_path / 'election_json'
outfile = dir_path / 'converted_scrapes.csv'

tables = []

for contest in scraped_dir.glob('*.json'):
    
    with open(contest) as f:
        results = json.load(f)

    raceID = ''.join(results['config']['jurisdiction'].split(' ')) + '_' + \
             ''.join(results['config']['date'].split('/')) + '_' + \
             ''.join(results['config']['contest'].split(' '))
    year = results['config']['date'].split('/')[0]

    candidate_tally = {k: {'raceID':raceID, 
                           'name': k,
                           'year': year, 
                           'winner': False, 
                           'round_count': len(results['results']), 
                           'round_elected': None, 
                           'round_eliminated': None, 
                           'counts': [],
                           'percents': []} 
                       for k in results['results'][0]['tally'].keys()}
    
    for round_num, tally_round in enumerate(results['results'], start=1):
        
        for candidate in candidate_tally.keys():
            candidate_tally[candidate]['counts'].append('')
        
        for candidate, count in tally_round['tally'].items():
            candidate_tally[candidate]['counts'][-1] = count
            
        total = sum(count for candidate, count in tally_round['tally'].items() if candidate != 'Inactive ballots')
        
        for candidate in candidate_tally.keys():
            candidate_tally[candidate]['percents'].append('')
            
        for candidate, count in tally_round['tally'].items():
            candidate_tally[candidate]['percents'][-1] = 100 * count / total
        
        percents = {candidate: 100 * count / total for candidate, count in tally_round['tally'].items() 
                    if candidate != 'Inactive ballots'}
        
        winners = [candidate for candidate, percent in percents.items() if percent > 50]
        losers = [candidate for candidate in percents.keys() if candidate not in winners]
        
        if len(winners) > 1:
            raise RuntimeError
        
        if len(winners) == 1:
            candidate_tally[winners[0]]['winner'] = True
            if candidate_tally[winners[0]]['round_elected'] is None:
                candidate_tally[winners[0]]['round_elected'] = round_num
            
            for loser in losers:
                if candidate_tally[loser]['round_eliminated'] is None:
                    candidate_tally[loser]['round_eliminated'] = round_num
            
        eliminated_candidates = [res['eliminated'] for res in tally_round['tallyResults'] if 'eliminated' in res]
        for candidate in eliminated_candidates:
            if candidate_tally[candidate]['round_eliminated'] is None:
                candidate_tally[candidate]['round_eliminated'] = round_num
    
    dicts = []
    for candidate_info in candidate_tally.values():
        
        for round_num, count in enumerate(candidate_info['counts'], start=1):
            candidate_info[f'round_{round_num:02}_vote'] = count
    
        # for round_num, percents in enumerate(candidate_info['percents'], start=1):
        #     candidate_info[f'round_{round_num:02}_percent'] = percents
        
        del candidate_info['counts']
        del candidate_info['percents']
        dicts.append(candidate_info)
        
    tables.append(pd.DataFrame(dicts))
        
pd.concat(sorted(tables, key=lambda x: -x.shape[1]), axis=0, sort=False, ignore_index=True).to_csv(outfile, index=False)


BLOCK_SIZE = 65536 # The size of each read from the file
file_hash = hashlib.sha256() # Create the hash object, can use something other than `.sha256()` if you wish
with open(outfile, 'rb') as f: # Open the file to read it's bytes
    fb = f.read(BLOCK_SIZE) # Read from the file. Take in the amount declared above
    while len(fb) > 0: # While there is still data being read from the file
        file_hash.update(fb) # Update the hash
        fb = f.read(BLOCK_SIZE) # Read the next block from the file

hashed_filename = dir_path / f'converted-scrapes-{file_hash.hexdigest()[:10]}.csv'
os.rename(outfile, hashed_filename)