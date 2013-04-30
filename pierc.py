#! /usr/bin/env python
#

#libs
from ircbot import SingleServerIRCBot
from irclib import nm_to_n, nm_to_h, irc_lower, ip_numstr_to_quad, ip_quad_to_numstr
import irclib
import sys
import re
import time
import datetime

#mine
import pierc_db
import config
import xmpp


# Configuration

class Logger(irclib.SimpleIRCClient):
	
	def __init__(self, server, port, channel, nick, 
				mysql_server, mysql_port, mysql_database,
				mysql_user, mysql_password, alert_list, bot_account, bot_password ):

	
		irclib.SimpleIRCClient.__init__(self)
		
		#IRC details
		self.server = server
		self.port = port
		self.target = channel
		self.channel = channel
		self.nick = nick
		
		#MySQL details
		self.mysql_server = mysql_server
		self.mysql_port = mysql_port
		self.mysql_database = mysql_database
		self.mysql_user = mysql_user
		self.mysql_password = mysql_password
		
		#Google Chat Details
		self.bot_account = bot_account
		self.bot_password = bot_password
		self.alert_list = alert_list
		
		#Regexes
		self.nick_reg = re.compile("^" + nick + "[:,](?iu)")
		
		#Message Cache
		self.message_cache = []		#messages are stored here before getting pushed to the db
		
		#Disconnect Countdown
		self.disconnect_countdown = 5
	
		self.last_ping = 0
		self.ircobj.delayed_commands.append( (time.time()+5, self._no_ping, [] ) )
	
		self.connect(self.server, self.port, self.nick)
	
	def _no_ping(self):
		if self.last_ping >= 1200:
			raise irclib.ServerNotConnectedError
		else:
			self.last_ping += 10
		self.ircobj.delayed_commands.append( (time.time()+10, self._no_ping, [] ) )


	def _dispatcher(self, c, e):
	# This determines how a new event is handled. 
		if(e.eventtype() == "topic" or 
		   e.eventtype() == "part" or
		   e.eventtype() == "join" or
		   e.eventtype() == "action" or
		   e.eventtype() == "quit" or
		   e.eventtype() == "nick" or
		   e.eventtype() == "pubmsg"):
			try: 
				source = e.source().split("!")[0]
			except IndexError:
				source = ""
			try:
				text = e.arguments()[0]
			except IndexError:
				text = ""
		
			# Prepare a message for the buffer
			message_dict = {"channel":"",
							"name": source,
							"message": text,
							"type": e.eventtype(),
							"time": str(datetime.datetime.utcnow()) }			
			try:
				message_dict["channel"] = e.target().strip('#')
			except AttributeError:
				pass
							
			if e.eventtype() == "nick":
				message_dict["message"] = e.target()
			
			# Most of the events are pushed to the buffer. 
			self.message_cache.append( message_dict )
		
		m = "on_" + e.eventtype()	
		if hasattr(self, m):
			getattr(self, m)(c, e)

	def _ask_for_help(self, send_to, message):
		jid=xmpp.JID(self.bot_account)
		user, server, password = jid.getNode(), jid.getDomain(), self.bot_password
		conn=xmpp.Client(server)
		conres=conn.connect( server=("jabber.org", 5222) )
		if not conres:
			print "Unable to connect to server %s!"%server
			sys.exit(1)
		if conres<>'tls':
			print "Warning: unable to estabilish secure connection - TLS failed!"
		authres=conn.auth(user, password)
		if not authres:
			print "Unable to authorize on %s - Plsese check your name/password."%server
			sys.exit(1)
		if authres<>"sasl":
			print "Warning: unable to perform SASL auth os %s. Old authentication method used!"%server
		pres=xmpp.Presence(priority=5, show="available", status="Looking for help")
		conn.send(pres)
		time.sleep(5)
		conn.send(xmpp.Message(send_to, message))
		#conn.disconnect()

	def on_nicknameinuse(self, c, e):
		c.nick(c.get_nickname() + "_")

	def on_welcome(self, connection, event):
		for chan in self.target:
			if irclib.is_channel(chan):
				connection.join(chan)

	def on_disconnect(self, connection, event):
		self.on_ping(connection, event)
		connection.disconnect()
		raise irclib.ServerNotConnectedError

	def on_ping(self, connection, event):
		self.last_ping = 0
		try:
			db = pierc_db.Pierc_DB( self.mysql_server,
															self.mysql_port,
															self.mysql_database, 
															self.mysql_user,
															self.mysql_password)
			for message in self.message_cache:
				db.insert_line(message["channel"], message["name"], message["time"], message["message"], message["type"] )
			
			db.commit()
			if self.disconnect_countdown < 5:
				self.disconnect_countdown = self.disconnect_countdown + 1
			
			del db
			# clear the cache
			self.message_cache = []	
				
		except Exception, e:
			print "Database Commit Failed! Let's wait a bit!" 
			print e
			if self.disconnect_countdown <= 0:
				sys.exit( 0 )
			for chan in self.channel:
				connection.privmsg(chan, "Database connection lost! " + str(self.disconnect_countdown) + " retries until I give up entirely!" )
			self.disconnect_countdown = self.disconnect_countdown - 1
			

	def on_pubmsg(self, connection, event):
		text = event.arguments()[0]

		# If you talk to the bot, this is how he responds.
		if self.nick_reg.search(text):
			if text.split(" ")[1] and text.split(" ")[1] == "quit":
				for chan in self.channel:
					connection.privmsg(chan, "Goodbye.")
				self.on_ping( connection, event )
				sys.exit( 0 ) 
				
			if text.split(" ")[1] and text.split(" ")[1] == "ping":
				self.on_ping(connection, event)
				return
				
	def on_privmsg(self, connection, event):
		text = event.arguments()[0]
		source = nm_to_n(event.source())
		if text.split()[0].lower() == "helpme":
			self._ask_for_help("jdwolford@gmail.com","We need help over here!")
			# self.bot.setState("online","Looking for help")
			# print"Alert List: "
			# print self.alert_list
			# for (channel, helpers) in self.alert_list:
			# 	for h in helpers:
			# 		print "asking " + h + " for help!"
			# 		self.bot.replyMessage(h, source + " is asking for help in IRC!")
			# 		connection.privmsg(source, "I have asked the the helper gnomes to come help")

def main():
	mysql_settings = config.config("mysql_config.txt")
	irc_settings = config.config("irc_config.txt")
	#summoner_bot = GtalkRobot()
	#summoner_bot.setState('available', "PyGtalkRobot")
	#summoner_bot.start("justinsbot@jabber.org", "greenbanana")
	
	c = Logger(
				irc_settings["server"][0], 
				int(irc_settings["port"][0]), 
				irc_settings["channel"], 
				irc_settings["nick"][0],
				mysql_settings["server"][0],
				int(mysql_settings["port"][0]),
				mysql_settings["database"][0],
				mysql_settings["user"][0],
				mysql_settings["password"][0],
				irc_settings["alert"],
				"justinsbot@jabber.org", "greenbanana" )
	while True:
		c.process_once(timeout=1)
		#summoner_bot.StepOn()
		time.sleep(1)
	
if __name__ == "__main__":
	irc_settings = config.config("irc_config.txt")
	reconnect_interval = irc_settings["reconnect"]
	while True:
		try:
			main()
		except irclib.ServerNotConnectedError:
			print "Server Not Connected! Let's try again!"             
			time.sleep(float(reconnect_interval))
			
