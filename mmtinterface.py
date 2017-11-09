# to run mmt server : cf. https://docs.python.org/3/library/subprocess.html
import subprocess
#subprocess.run(["ls", "-l", "/dev/null"], stdout=subprocess.PIPE) # TODO
#for now, running
# mmt
# extension info.kwarc.mmt.interviews.InterviewServer
# server on 8080
#TODO ask dennis on whether and how to delete modules

# to do http requests
#http://docs.python-requests.org/en/master/user/quickstart/
import requests
from requests.utils import quote
from lxml import etree
from openmath import openmath

class MMTServerError(Exception):
    def __init__(self, err):
        self.error = err
        super(MMTServerError, self).__init__("MMT server error: " + str(self.error))


class MMTReply:
    def __init__(self, mmtinterface, theorypath):
        # theorypath is relative for now
        self.theorypath = theorypath
        (self.ok, self.root) = mmtinterface.query_for(theorypath)
        if not self.ok:
            raise MMTServerError(etree.tostring(self.root, pretty_print=True).decode())
        for element in self.root.iter("div"):
            if (element.get('class')) == 'error':
                self.ok = False
                for child in element:
                    if (child.get('class')) == 'message':
                        raise MMTServerError(child.text)

    def getConstant(self, constantname):
        elements = self.getConstants()
        #print ("elements: " + str(elements))
        for element in elements:
            #print(element.get('name'))
            if element.get('name') == constantname:
                return element

    def getConstants(self):
        elements = []
        for element in self.root.iter("constant"):
            #print("Constant: %s - %s - %s" % (element, element.text, element.keys()))
            elements.append(element)
        return elements

    def getDefinition(self, constantname):
        element = self.getConstant(constantname)
        if element is not None:
            for child in element:
                if (child.tag) == 'definition':
                    #printElement(child)
                    return child

    def getType(self, constantname):
        element = self.getConstant(constantname)
        if element is not None:
            for child in element:
                if (child.tag) == 'type':
                    #printElement(child)
                    return child

#(probably volatile) accesses to concrete data structures
#class InterviewHelper:
    def getIntervalBoundaries (self, mmtreply, intervalname):
        child = mmtreply.getDefinition(intervalname)
        for oms in child.iter("{*}OMS"):
            #print("OMS: %s - %s - %s" % (oms, oms.text, oms.keys()))
            if (oms.get('name') == 'ccInterval'):
                a = oms.getnext()
                b = a.getnext()
                #print("a: %s - %s - %s" % (a, a.text, a.get('value')))
                #print("b: %s - %s - %s" % (b, b.text, b.get('value')))
                return (a.get('value'), b.get('value'))


def printElement(element):
    print (etree.tostring(element, pretty_print=True).decode())

class MMTInterface:
    def __init__(self):
        # set parameters for communication with mmt server
        self.serverInstance = 'http://localhost:8080'
        self.extension = ':interview'
        self.URIprefix = 'http://mathhub.info/'
        self.namespace = 'MitM/smglom/calculus' #TODO
        self.debugprint = False

    def mmt_new_theory(self, thyname):
        #So, ich hab mal was zu MMT/devel gepusht. Es gibt jetzt eine Extension namens InterviewServer. Starten tut man die mit "extension info.kwarc.mmt.interviews.InterviewServer"
        #Wenn du dann in MMT den Server (sagen wir auf Port 8080) startest, kannst du folgende HTTP-Requests ausführen:
        #"http://localhost:8080/:interview/new?theory="<MMT URI>"" fügt eine neue theorie mit der uri <MMT URI> hinzu
        req = '/' + self.extension + '/new?theory=' + self.get_mpath(thyname) + '&meta=http://mathhub.info/MitM/Foundation?Logic'
        return self.http_request(req)

    def mmt_new_view(self, viewname, fromtheory, totheory):
        # analog für ?view="<MMT URI>".
        req = '/' + self.extension + '/new?view=' + self.get_mpath(viewname) + '&from=' + self.get_mpath(fromtheory) + '&to=' + self.get_mpath(totheory)
        return self.http_request(req)

    def mmt_new_decl(self, declname, thyname, declcontent):
        #".../:interview/new?decl="<irgendwas>"&cont="<MMT URI>" ist der query-path um der theorie <MMT URI> eine neue declaration hinzuzufügen (includes, konstanten...). Die Declaration sollte dabei in MMT-syntax als text im Body des HTTP-requests stehen.
        post = '/' + self.extension + '/new?decl=' + declname + '&cont=' + self.get_mpath(thyname)
        return self.http_request(post, add_dd(declcontent))

    def mmt_new_term(self, termname, thyname, termcontent):
        #analog für ".../:interview/new?term="<irgendwas>"&cont="<MMT URI>" für terme - nachdem da nicht klar ist was der server damit tun sollte gibt er den geparsten term als omdoc-xml zurück (wenn alles funktioniert)
        post = '/' + self.extension + '/new?term=' + termname + '&cont=' + self.get_mpath(thyname)
        return self.http_request(post, termcontent)

    def http_request(self, message, data=None):
        url = self.serverInstance + (message)
        print(url) if self.debugprint else 0
        session = requests.Session()
        adapter = requests.adapters.HTTPAdapter()
        session.mount('https://', adapter)
        session.mount('http://', adapter)
        try:
            if data:
                binary_data = data.encode('UTF-8')
                print('\n' + str(data)) if self.debugprint else 0
                headers = {'content-type': 'application/json',
                            'content-encoding': 'UTF-8'}
                req = session.post(url, data=binary_data, headers=headers, stream=True)
            else:
                req = requests.get(url)
        except ConnectionError as error: #this seems to never be called
            print(error)
            print("Are you sure the mmt server is running?")
            raise SystemExit
        if req.text.startswith('<'):
            root = etree.fromstring(req.text)
            if root is not None:
                printElement(root)
        if req.status_code == 200:
            return True
        if not req.text.startswith('<'):
            print(req.text)
        return (False, req.text)

    def get_mpath(self, thyname):
        mpath = self.URIprefix + self.namespace + thyname #TODO
        return mpath

    def query_for(self, thingname):
        #this here just stolen from what MMTPy does
        #querycontent = b'<function name="presentDecl" param="xml"><literal><uri path="http://mathhub.info/MitM/smglom/algebra?magma"/></literal></function>'
        querycontent = '<function name="presentDecl" param="xml"><literal><uri path="' + self.get_mpath( thingname )+ '"/></literal></function>'
        return self.http_qrequest(querycontent)

    def http_qrequest(self, data, message='/:query'):
        #print(self.serverInstance + message)
        session = requests.Session()
        adapter = requests.adapters.HTTPAdapter()
        session.mount('https://', adapter)
        session.mount('http://', adapter)
        #print('\n' + str(data))
        binary_data = data.encode('UTF-8')
        headers = {'content-type': 'application/xml'}
        req = session.post((self.serverInstance + message), data=binary_data, headers=headers, stream=True)
        root = etree.fromstring(req.text)
        if req.status_code == 200:
            return (True, root)
        return (False, root)

def add_dd(string):
    return string + "❙"
