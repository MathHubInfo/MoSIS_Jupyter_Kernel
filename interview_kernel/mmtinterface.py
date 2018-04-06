# to run mmt server : cf. https://docs.python.org/3/library/subprocess.html
import subprocess
import psutil
import time
# for now, running
# java -jar /home/freifrau/Desktop/masterarbeit/mmt/deploy/mmt.jar --file=server-interview.msl --keepalive
# or
# mmt
# extension info.kwarc.mmt.interviews.InterviewServer
# server on 8080
import threading
# TODO ask dennis on whether and how to delete modules

# to do http requests
# http://docs.python-requests.org/en/master/user/quickstart/
import requests
from requests.utils import quote
from contextlib import closing
#from urllib.parse import urlencode # is what we actually want to use
from lxml import etree
#from openmath import openmath


def start_mmt_server(port_number, mmtjar):
    """starts the mmt server as a separate subprocess"""
    p = subprocess.run(["/usr/bin/java", "-jar", mmtjar, # "--file=server-interview.msl",
                          "server", "on", str(port_number), "--keepalive"],
                          stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out = p.stdout
    if p.returncode != 0 and p.returncode != 130:  # if not closed gracefully or through ctrl-c
        raise MMTServerError("Server aborted, return code " + str(p.returncode) + ", " + str(out))


def exit_mmt_server(port_number, mmtjar, timeout=3.0):
    """tries to shutdown the mmt server process"""
    completed = subprocess.run(["/usr/bin/java", "-jar", mmtjar, ":send", str(port_number),
                                "exit"],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if completed.stdout != None and "(Connection refused)" in str(completed.stdout):
        if timeout > 0.0:
            exit_mmt_server(port_number, mmtjar, timeout - 0.1)


def start_mmt_extension(port_number, mmtjar, timeout=3.0):
    """starts the interview extension for mmt"""
    time.sleep(0.1)  # hope for server to have started communication already
    completed = subprocess.run(["/usr/bin/java", "-jar", mmtjar, ":send", str(port_number),
                  "extension", "info.kwarc.mmt.interviews.InterviewServer"],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if completed.stdout != None and "(Connection refused)" in str(completed.stdout):
        if timeout > 0.0:
            start_mmt_extension(port_number, mmtjar, timeout-0.1)
        else:
            raise MMTServerError("unable to start interview extension")


def start_mmt_relational_reader(port_number, mmtjar, timeout=3.0):
    """starts the relational reader mmt server extension, which is required for some tgview graph types
            attention: this loads everything in the local mathhub folder, can take some time depending on your files"""
    completed = subprocess.run(["/usr/bin/java", "-jar", mmtjar, ":send", str(port_number),
                  "extension", "info.kwarc.mmt.api.ontology.RelationalReader"],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if completed.stdout != None and "(Connection refused)" in str(completed.stdout):
        if timeout > 0.0:
            start_mmt_extension(port_number, mmtjar, timeout-0.1)
        else:
            raise MMTServerError("unable to start interview extension")


def find_free_port():
    import socket
    port_number = 0
    while (port_number < 1024) or (8888 < port_number < 10000):
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s1:
            s1.bind(('localhost', 0))            # Bind to a free port provided by the host.
            port_number = s1.getsockname()[1]
    return port_number  # Return the port number assigned.


def run_mmt(mmtjar, port_number=None):
    if port_number is None:
        port_number = find_free_port()

    t1 = threading.Thread(target=start_mmt_server, args=(port_number, mmtjar), daemon=True)
    t1.start()

    start_mmt_extension(port_number, mmtjar)
    start_mmt_relational_reader(port_number, mmtjar)

    #t2 = threading.Thread(target=start_mmt_extension, args=[port_number], daemon=True)
    #t2.start()
    return port_number


class MMTServerError(Exception):
    def __init__(self, err, longerr=None):
        self.error = err
        self.longerr = longerr
        super(MMTServerError, self).__init__("MMT server error: " + str(self.error), longerr)


class MMTReply:
    """An object that holds
        ok : whether the request was successful and
        root: the returned answer, usually an etree holding the xml reply"""

    def __init__(self, ok, root=None):
        self.ok = ok
        self.root = root
        #        print("creating reply")
        #        print(root)
        if isinstance(root, etree._Element):
            for element in root.iter():
                # for element in root.iter("div"): # why not entering this loop?
                # print("for element " + elementToString(element))
                if (element.get('class')) == 'error':
                    self.ok = False
                    for child in element:
                        if (child.get('class')) == 'message':
                            raise MMTServerError(child.text, element_to_string(self.root))
        if not self.ok:
            raise MMTServerError(element_to_string(self.root))

    def getConstant(self, constantname):
        elements = self.getConstants()
        # print ("elements: " + str(elements))
        for element in elements:
            if element.get('name') == constantname:
                return element

    def getConstants(self):
        elements = []
        for element in self.root.iter("constant"):
            # print("Constant: %s - %s - %s" % (element, element.text, element.keys()))
            elements.append(element)
        return elements

    def hasDefinition(self, constantname):
        if self.getDefinition(constantname) is not None:
            return True

    def getDefinition(self, constantname):
        element = self.getConstant(constantname)
        if element is not None:
            for child in element:
                if (child.tag) == 'definition':
                    # print(elementToString(child))
                    return child

    def getType(self, constantname):
        element = self.getConstant(constantname)
        if element is not None:
            for child in element:
                if (child.tag) == 'type':
                    print(element_to_string(child))
                    #return child
                    for oms in child.iter("{*}OMS"):
                        return self.get_name_or_expand_if_arrow(oms)

    def get_name_or_expand_if_arrow(self, oms):
        name = oms.get('name')
        if name == 'arrow':
            next = oms.getnext()
            name = next.get('name')
            while next.getnext() is not None:
                next = next.getnext()
                name = name + " ⟶ " + next.get('name')
        return name

    # (probably very volatile) accesses to concrete data structures
    def getIntervalBoundaries(self, mmtreply, intervalname):
        child = mmtreply.getDefinition(intervalname)
        for oms in child.iter("{*}OMS"):
            #print("OMS: %s - %s - %s" % (oms, oms.text, oms.keys()))
            if (oms.get('name') == 'interval'):
                a = oms.getnext()
                b = a.getnext()
                #print("a: %s - %s - %s" % (a, a.text, a.get('value')))
                #print("b: %s - %s - %s" % (b, b.text, b.get('value')))
                return (a.get('value'), b.get('value'))

    def tostring(self):
        return element_to_string(self.root)

    def inferred_type_to_string(self):
        type_string = ""
        for mo in self.root.iter("{*}mo"):
            type_string = type_string + " " + mo.text
        return type_string.strip()


def element_to_string(element):
    return etree.tostring(element, pretty_print=True).decode('utf8')


class MMTInterface:
    def __init__(self, mmt_jar="/home/freifrau/Desktop/masterarbeit/mmt/deploy/mmt.jar"):
        self.mmt_jar = mmt_jar
        self.port_number = run_mmt(self.mmt_jar)  # , port_number)
        # set parameters for communication with mmt server
        self.serverInstance = 'http://localhost:'+str(self.port_number)
        self.extension = ':interview'
        self.URIprefix = 'http://mathhub.info/'
        self.namespace = self.URIprefix + 'MitM/smglom/calculus/differentialequations'  # TODO
        self.debugprint = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.exit_mmt()

    def __del__(self):
        self.exit_mmt()

    def exit_mmt(self):
        exit_mmt_server(self.port_number, self.mmt_jar)

    def mmt_new_theory(self, thyname):
        # So, ich hab mal was zu MMT/devel gepusht. Es gibt jetzt eine Extension namens InterviewServer. Starten tut man die mit "extension info.kwarc.mmt.interviews.InterviewServer"
        # Wenn du dann in MMT den Server (sagen wir auf Port 8080) startest, kannst du folgende HTTP-Requests ausführen:
        # "http://localhost:8080/:interview/new?theory="<MMT URI>"" fügt eine neue theorie mit der uri <MMT URI> hinzu
        req = '/' + self.extension + '/new?theory=' + quote(self.get_mpath(
            thyname)) + '&meta=' + quote('http://mathhub.info/MitM/Foundation?Logic')
        return self.http_request(req)

    def mmt_new_view(self, viewname, fromtheory, totheory):
        # analog für ?view="<MMT URI>".
        req = '/' + self.extension + '/new?view=' + quote(self.get_mpath(viewname)) + '&from=' + quote(self.get_mpath(
            fromtheory)) + '&to=' + quote(self.get_mpath(totheory))
        return self.http_request(req)

    def mmt_new_decl(self, declname, thyname, declcontent):
        # ".../:interview/new?decl="<irgendwas>"&cont="<MMT URI>" ist der query-path um der theorie <MMT URI> eine neue declaration hinzuzufügen (includes, konstanten...). Die Declaration sollte dabei in MMT-syntax als text im Body des HTTP-requests stehen.
        post = '/' + self.extension + '/new?decl=d&cont=' + quote(self.get_mpath(thyname))
        return self.http_request(post, add_dd(declcontent))

    def mmt_new_term(self, termname, thyname, termcontent):
        # analog für ".../:interview/new?term="<irgendwas>"&cont="<MMT URI>" für terme - nachdem da nicht klar ist was der server damit tun sollte gibt er den geparsten term als omdoc-xml zurück (wenn alles funktioniert)
        post = '/' + self.extension + '/new?term=' + quote(termname) + '&cont=' + quote(self.get_mpath(thyname))
        return self.http_request(post, termcontent)

    def mmt_infer_type(self, thyname, termcontent):
        post = '/' + self.extension + '/infer?cont=' + quote(self.get_mpath(thyname))
        return self.http_request(post, termcontent)

    def http_request(self, message, data=None):
        url = self.serverInstance + message
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
        except ConnectionError as error:  # this seems to never be called
            print(error)
            print("Are you sure the mmt server is running?")
            raise SystemExit
        # print(req.text) if self.debugprint else 0
        if req.text.startswith('<'):
            root = etree.fromstring(req.text)
        else:
            root = None
        if req.status_code == 200:
            return MMTReply(True, root)
        return MMTReply(False, root)

    def get_mpath(self, thyname):
        mpath = thyname
        if not (mpath.startswith("http://") or mpath.startswith("https://")):
            mpath = self.namespace + "?" + thyname  # TODO
        return mpath

    def query_for(self, thingname):
        # this here just stolen from what MMTPy does
        # querycontent = b'<function name="presentDecl" param="xml"><literal><uri path="http://mathhub.info/MitM/smglom/algebra?magma"/></literal></function>'
        querycontent = '<function name="presentDecl" param="xml"><literal><uri path="' + (self.get_mpath(thingname)) + '"/></literal></function>'

        return self.http_qrequest(querycontent)

    def http_qrequest(self, data, message='/:query'):
        url = self.serverInstance + message
        print(url) if self.debugprint else 0
        session = requests.Session()
        adapter = requests.adapters.HTTPAdapter()
        session.mount('https://', adapter)
        session.mount('http://', adapter)
        print('\n' + str(data)) if self.debugprint else 0
        binary_data = data.encode('UTF-8')
        headers = {'content-type': 'application/xml'}
        req = session.post(url, data=binary_data, headers=headers, stream=True)
        root = etree.fromstring(req.text)
        if req.status_code == 200:
            return MMTReply(True, root)
        return MMTReply(False, root)


def add_dd(string):
    if string.endswith("❙") or string.endswith("❚"):
        return string
    return string + "❙"
