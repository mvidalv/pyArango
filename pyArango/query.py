import requests
import json

from document import Document, Edge
from theExceptions import AQLQueryError, SimpleQueryError
import collection as COL

class RawCursor(object) :
	"a raw interface to cursors that returns json"
	def __init__(self, database, cursorId) :
		self.database = database
		self.id = cursorId
		self.URL = "%s/cursor/%s" % (self.database.URL, self.id)

	def next(self) :
		"returns the next batch"
		r = requests.put(self.URL)
		data = r.json()
		if r.status_code == 400 :
			raise CursorError(data["errorMessage"], self.id, data)
		return r.json()

class Query(object) :
	"This class abstract and should not be instanciated"

	def __init__(self, request, database, rawResults) :
		"if rawResults = True, will always return the json representation of the results and not a Document object. queryPost contains a dictionnary representation of the initial POST payload sent to the database"

		self.rawResults = rawResults
		self.response = request.json()
		self.database = database
		self._developed = set()
		if request.status_code == 201 or request.status_code == 200:
			self.batchNumber = 1
			try : #if there's only one element
				self.response = {"result" : [self.response["document"]], 'hasMore' : False}
				del(self.response["document"])
			except KeyError :
				pass

			if self.response["hasMore"] :
				self.cursor = RawCursor(self.database, self.id)
			else :
				self.cursor = None
		elif request.status_code == 404 :
			self.batchNumber = 0
			self.result = []
		else :
			self._raiseInitFailed(request)
	
	def _raiseInitFailed(self, request) :
		"must be implemented in child, this called if the __init__ fails"
		raise NotImplemented("Must be implemented in child")

	def _developDoc(self, i) :
		docJson = self.result[i]
		try :
			collection = self.database[docJson["_id"].split("/")[0]]
		except KeyError :
			raise CreationError("result %d is not a valid Document. Try setting rawResults to True" % i)

		if collection.type == COL.COLLECTION_EDGE_TYPE :
			self.result[i] = Edge(collection, docJson)
 		else :
 			self.result[i] = Document(collection, docJson)

	def nextBatch(self) :
		"become the next batch. raises a StopIteration if there is None"
		self.batchNumber += 1
		if not self.response["hasMore"] or self.cursor is None :
			raise StopIteration("That was the last batch")

		self.response = self.cursor.next()
		self._developed = set()

	def delete(self) :
		"kills the cursor"
		requests.delete(self.cursor)

	def __getitem__(self, i) :
		"returns a ith result of the query."
		if not self.rawResults and (i not in self._developed) : 
			self._developDoc(i)
			self._developed.add(i)
		return self.result[i]

	def __len__(self) :
		return len(self.result)

	def __getattr__(self, k) :
		try :
			resp = object.__getattribute__(self, "response")
			return resp[k]
		except (KeyError, AttributeError) :
			raise  AttributeError("There's not attribute %s" %(k))

class AQLQuery(Query) :
	"AQL queries are attached to a database"
	def __init__(self, database, query, rawResults, batchSize, bindVars, options, count, fullCount) :
		payload = {'query' : query, 'batchSize' : batchSize, 'bindVars' : bindVars, 'options' : options, 'count' : count, 'fullCount' : fullCount}
		
		self.query = query
		self.database = database
		request = requests.post(database.cursorsURL, data = json.dumps(payload))
		Query.__init__(self, request, database, rawResults)

	def _raiseInitFailed(self, request) :
		data = request.json()
		raise AQLQueryError(data["errorMessage"], self.query, data)

class Cursor(Query) :
	"Cursor queries are attached to a database, use them to continue where you left"
	def __init__(self, database, cursorId, rawResults) :
		self.rawResults = rawResults
		self._developed = set()
		self.batchNumber = 1
		self.cursor = RawCursor(database, cursorId)
		self.response = self.cursor.next()

	def _raiseInitFailed(self, request) :
		data = request.json()
		raise CursorError(data["errorMessage"], self.id, data)


class SimpleQuery(Query) :
	"Simple queries are attached to a single collection"
	def __init__(self, collection, queryType, batchSize, rawResults, **queryArgs) :

		self.collection = collection
		payload = {'collection' : collection.name, 'batchSize' : batchSize}
		payload.update(queryArgs)
		payload = json.dumps(payload)
		URL = "%s/simple/%s" % (collection.database.URL, queryType)

		request = requests.put(URL, data = payload)

		Query.__init__(self, request, collection.database, rawResults)

	def _raiseInitFailed(self, request) :
		data = request.json()
		raise SimpleQueryError(data["errorMessage"], data)

	def _developDoc(self, i) :
		docJson = self.result[i]
		if self.collection.type == COL.COLLECTION_EDGE_TYPE :
			self.result[i] = Edge(self.collection, docJson)
 		else :
 			self.result[i] = Document(self.collection, docJson)