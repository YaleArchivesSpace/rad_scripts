#!/usr/bin/python3

import csv
import json
import pprint
import requests

'''
RAD update functions
'''

def login(url=None, username=None, password=None):
    """Logs into the ArchivesSpace API"""
    import requests
    try:
        if url is None and username is None and password is None:
            url = input('Please enter the ArchivesSpace API URL: ')
            username = input('Please enter your username: ')
            password = input('Please enter your password: ')
        auth = requests.post(url+'/users/'+username+'/login?password='+password).json()
        #if session object is returned then login was successful; if not it failed.
        if 'session' in auth:
            session = auth["session"]
            h = {'X-ArchivesSpace-Session':session, 'Content_Type': 'application/json'}
            print('Login successful!')
            logging.debug('Success!')
            return (url, h)
        else:
            print('Login failed! Check credentials and try again.')
            logging.debug('Login failed')
            logging.debug(auth.get('error'))
            #try again
            u, heads = login()
            return u, heads
    except:
        print('Login failed! Check credentials and try again!')
        logging.exception('Error: ')
        u, heads = login()
        return u, heads


def split_name(name_form):
	'''For the ~150 agents in this list, all are split into 2-3 item lists,
	either a primary name/rest of name or primary name/rest of name/dates list'''
	split_name_form = name_form.split(', ')
	if len(split_name_form) == 1:
		return {'primary_name' : '', 'rest_of_name': '', 'dates': ''}
	if len(split_name_form) == 2:
		return {'primary_name': split_name_form[0], 'rest_of_name': split_name_form[1], 'dates': ''}
	elif len(split_name_form) == 3:
		return {'primary_name': split_name_form[0], 'rest_of_name': split_name_form[1], 'dates': split_name_form[2]}
	else:
		print(len(split_name_form))

def compare_sort_name(preferred_name, variant_name, name_list):
	'''Also want to get the index of the display name and the authorized name(s)'''
	sort_dict = {}
	for i, name in enumerate(name_list):
		#print(f"	{name.get('sort_name')} {name.get('is_display_name')} {name.get('authorized')}")
		if name.get('authority_id') is not None:
			sort_dict['authority_id'] = name.get('authority_id')
			sort_dict['authorized_name'] = name.get('sort_name')
		if name.get('authorized') == True:
			sort_dict['authorized_index'] = i
		if name.get('is_display_name') == True:
			sort_dict['display_index'] = i
			sort_dict['existing_display_name'] = name.get('sort_name')
			if preferred_name == name.get('sort_name'):
				sort_dict['same_as_display'] = 'Y'
		if name.get('sort_name') == preferred_name:
			sort_dict['preferred_name_index'] = i
		if name.get('sort_name') == variant_name:
			sort_dict['variant_name_index'] = i
	return sort_dict

def prep_data_helper(api_url, sesh, reader, writer):
	for row in reader:
		agent_data = split_name(row['preferred_name'])
		agent_data['uri'] = row['uri']
		agent_data['action'] = row['action']
		agent_data['preferred_name'] = row['preferred_name']
		agent_data['bioghist'] = row['bioghist']
		if row['variant_1'] != '':
			agent_data['variant_name'] = row['variant_1']
		record_json = sesh.get(f"{api_url}{row['uri']}").json()
		if 'error' in record_json:
			agent_data['not_found_in_test'] = 'Y'
		names = record_json.get('names')
		if names:
			name_data = compare_sort_name(row['preferred_name'], row['variant_1'], names)
			agent_data.update(name_data)
		writer.writerow(agent_data)

def prep_data(api_url, sesh):
	csv_path = input('Please enter path to input CSV: ')
	csv_out_path = input('Please enter path to output CSV: ')
	with open(csv_path, 'r', encoding='utf8') as infile, open(csv_out_path, 'a', encoding='utf8') as outfile:
		reader = csv.DictReader(infile)
		fieldnames = ['action', 'uri', 'bioghist', 'preferred_name', 'primary_name', 'rest_of_name', 'dates', 'preferred_name_index', 'variant_name', 'variant_name_index', 'not_found_in_test', 'authorized_index', 'display_index', 'authority_id', 'authorized_name', 'same_as_display', 'existing_display_name']
		writer = csv.DictWriter(outfile, fieldnames=fieldnames)
		writer.writeheader()
		prep_data_helper(api_url, sesh, reader, writer)

def create_bioghist(record_json, bioghist):
	new_bioghist = {'jsonmodel_type': 'note_bioghist', 'publish': True, 'subnotes': [{'content': bioghist, 'jsonmodel_type': 'note_text', 'publish': True}]}
	if record_json.get('notes') is not None:
		record_json['notes'].append(new_bioghist)
		return record_json
	else:
		print(f'No notes key for record {uri} in row {i}')

def reset_name_booleans(record_json, authorized_index, display_index, value):
	record_json['names'][int(display_index)]['is_display_name'] = value
	record_json['names'][int(authorized_index)]['authorized'] = value
	return record_json

def update_name_indices(record_json, preferred_name_index, authorized_index, display_index):
	record_json = reset_name_booleans(record_json, preferred_name_index, preferred_name_index, True)
	record_json = reset_name_booleans(record_json, authorized_index, display_index, False)
	return record_json

def create_name_form(record_json, primary_name, rest_of_name, dates, authorized_index, display_index):
	# this changes the existing display and authorized names to False
	record_json = reset_name_booleans(record_json, authorized_index, display_index, False)
	new_name_form = {'jsonmodel_type': 'name_person', 'authorized': True, 'is_display_name': True, 'name_order': 'inverted', 'primary_name': primary_name, 'rest_of_name': rest_of_name, 'sort_name_auto_generate': True, 'source': 'local'}
	if dates != '':
		new_name_form['dates'] = dates
	record_json['names'].insert(0, new_name_form)
	return record_json

def rem_prefix(record_json):
	# maybe not the best way but it works for now
	display_name = record_json['names'][0]
	if 'prefix' in display_name:
		del record_json['names'][0]['prefix']
	return record_json

def update_names(record_json, preferred_name_index, authorized_index, display_index, primary_name, rest_of_name, dates, remove_prefix):
	if preferred_name_index != '':
		record_json = update_name_indices(record_json, preferred_name_index, authorized_index, display_index)
	elif remove_prefix != '':
		record_json = rem_prefix(record_json)
	else:
		record_json = create_name_form(record_json, primary_name, rest_of_name, dates, authorized_index, display_index)
	return record_json

def check_for_lc_uri(record_json):
	for name in record_json['names']:
		if name.get('authority_id') != None and name.get('authorized') == False:
			name['authorized'] = True
		if name.get('authority_id') == None and name.get('authorized') == True:
			name['authorized'] = False
	return record_json

def update_data(api_url, sesh, csv_path):
	with open(csv_path, 'r', encoding='utf8') as infile:
		csvfile = csv.reader(infile)
		next(csvfile)
		for i, row in enumerate(csvfile, 1):
			action = row[0]
			uri = row[1]
			bioghist = row[2]
			primary_name = row[4]
			rest_of_name = row[5]
			dates = row[6]
			preferred_name_index = row[7]
			authorized_index = row[11]
			display_index = row[12]
			remove_prefix = row[13]
			record_json = sesh.get(f"{api_url}{uri}").json()
			if not record_json.get('error'):
				if action == 'Update name form':
					record_json = update_names(record_json, preferred_name_index, authorized_index, display_index, primary_name, rest_of_name, dates, remove_prefix)
				elif action == 'Update name form; add biog note':
					record_json = update_names(record_json, preferred_name_index, authorized_index, display_index, primary_name, rest_of_name, dates, remove_prefix)
					record_json = create_bioghist(record_json, bioghist)
				elif action == 'Add biog note':
					record_json = create_bioghist(record_json, bioghist)
				else:
					print(f"Invalid action: {action} for record {uri} in row {i}")
				# not great
				#record_json = check_for_lc_uri(record_json)
				record_post = sesh.post(f"{api_url}{uri}", json=record_json).json()
				print(record_post)
			else:
				print(record_json)
				print(row)


def main():
	with requests.Session() as sesh:
		api_url, headers = login()
		csv_path = input('Please enter path to CSV: ')
		sesh.headers.update(headers)
		update_data(api_url, sesh, csv_path)
		#prep_data(api_url, sesh)
		

if __name__ == "__main__":
	main()