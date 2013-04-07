import ast


def config(filename):
	""" Process a file (located at filename)
		containing a series of key-value pairs
		this: awesome
		numkids: 10
		funk: soulbrother
		Into a dictionary. (dict[this] = "awesome")
	"""
	try:
		config_data = dict()
		db_file = open(filename, "r")
		for line in db_file:
			if line.startswith("#"):
				continue
			temp = line.replace(":", "").split()
			if temp[0] == "alert":
				key = temp[0]
				value = ast.literal_eval(line.split(None, 1)[1])
			else:	
				key = temp[0]
				value = temp[1:]
			config_data[key] = value
		db_file.close()
		return config_data
	except IOError:
		print filename, "missing."
		exit();

if __name__ == "__main__":
	irc_config = config("mysql_config.txt")
	for key,value in irc_config.iteritems():
		print key, value
