#!/usr/bin/env python
#
# Copyright (c) 2010-2011 MontaVista Software, LLC.  All rights reserved.
#
# This file is licensed under the terms of the GNU General Public License
# version 2. This program is licensed "as is" without any warranty of any
# kind, whether express or implied.
#
# mvl-content
#
# This tool to migrate mvl project

from optparse import OptionParser, OptionGroup
import os
import sys
import subprocess
import logging
import time
import shutil
import pickle
import base64
import urllib2
import socket
import cookielib
import tempfile
from urlparse import urlparse
import getpass
from xml.dom.minidom import parse, getDOMImplementation
from xml.parsers.expat import ExpatError
from ConfigParser import ConfigParser
import ssl
try :
   ssl._create_default_https_context = ssl._create_unverified_context
except:
   pass
import urllib
from urllib import splittype, splithost, splituser, splitpasswd

ContentToolVersion = "1.8"

pretty_print = lambda f: '\n'.join([line for line in f.toprettyxml(indent=' ' * 2).split('\n') if line.strip()])
class CookieMap(object):
    def __init__(self, username=None, cookieDir=None):
        self.__cookieDir = cookieDir
        self.__username = username
    def getCookieDir(self):
        return self.__cookieDir
    def getUsername(self):
        return self.__username
    def setUsername(self, username):
        self.__username = username
    def setCookieDir(self, cookieDir):
        self.__cookieDir = cookieDir
class CmdOptions(object):
    """class to define command line options for running mvl-migrate-project
    """
    def configureOptionParser(self):

        parser.add_option("-u", "--username", dest="username", default=None, help="set content site username", metavar="<username>")
        parser.add_option("-p", "--password", dest="password", default=None, help="set content site password", metavar="<password>")
        parser.add_option("--uri", dest="uri", default=None, help="set uri", metavar="<uri>")

        parser.add_option("-a", "--add", action="store_const", const="add", dest="operation", default="list", help="perform add operation")
        parser.add_option("-r", "--remove", action="store_const", const="remove", dest="operation", default="list", help="perform remove operation")
        parser.add_option("-l", "--list", action="store_const", const="list", dest="operation", default="list", help="perform list operation")


        debugGroup = OptionGroup(parser, "Debug Options")
        parser.add_option_group(debugGroup)
        debugGroup.add_option("-d", "--debug", action="store_true", dest="isDebug", default=False, help="print debug messages")

        group = OptionGroup(parser, "Advance Options",
                    "Caution: do not use --urlprefix and --content-xml-dir together")
        parser.add_option_group(group)
        group.add_option("--content-cache-dir", dest="contentCacheDir", default=None, help="set mvl content cache directory", metavar="<content-cache-dir>")

        group.add_option("--use-wget", action="store_true", dest="wget", default=False, help="use wget instead of urllib2 as the default tools to download")
        group.add_option("--missing-ok", action="store_true", dest="missingok", default=False, help="ok if the file is not available for download. do not report download error messages")
        group.add_option("--non-interactive", action="store_true", dest="noninteractive", default=False, help="no interaction between mvl-project and user. If a parameter needed has no default value and user does not provide a value using arguments, mvl-project will fail.")
        group.add_option("--timeout", type="int", dest="defaulttimeout", default=60, help="specify timeout in seconds for blocking operation like the connection attempt. default is 60 seconds")

class ContentCache:
    def __init__(self) :
        self.__cacheParentDir = None
        self.__initialized = False
        self.__cacheMapPath = None
        self.__cacheMap = {}
        self.__cookieMapDictionary = {}
        self.__cookieMapPath = None

    def getCacheParentDir(self):
        if self.__initialized == False :
            self.loadMaps()
        return self.__cacheParentDir

    def validateContentCacheDir(self):
        contentCacheDir = None
        if options.contentCacheDir != None and options.contentCacheDir != '':
            contentCacheDir = os.path.abspath(os.path.expanduser(options.contentCacheDir))
        else :
            try:
                envDir = os.environ["CONTENT_CACHE_DIR"]
                contentCacheDir = os.path.abspath(os.path.expanduser(envDir))
            except KeyError:
                pass

        parentDir = None
        if contentCacheDir != None and contentCacheDir != '' :
            exists = os.path.exists(contentCacheDir)
            if not exists :
                os.makedirs(contentCacheDir)
            dotContentDir=os.path.join(contentCacheDir,'.mvl-content')
            dotContentExists = os.path.exists(dotContentDir)
            if not dotContentExists:
               os.makedirs(dotContentDir)

            if not os.path.isdir(contentCacheDir) :
                sys.stderr.write('Error: expecting a directory path for content cache path. Exiting.\n')
                logger.log(logging.DEBUG, 'program exists with error code 1\n')
                sys.exit(1)
            parentDir = contentCacheDir
        elif hasattr(options, 'projectdir') and options.projdir != None :
            parentDir = self.findCacheMapDir(options.projdir)
        if parentDir == None :
            parentDir = os.path.join(tempfile.gettempdir(), getpass.getuser())

        self.__cacheParentDir = os.path.join(parentDir, '.mvl-content')

        if not os.path.exists(self.__cacheParentDir) :
            os.makedirs(self.__cacheParentDir)

        self.__cacheMapPath = os.path.join(self.__cacheParentDir, '.cacheMap')
        self.__cookieMapPath = os.path.join(self.__cacheParentDir, '.cookieMap')

    def loadMaps(self) :
        self.validateContentCacheDir()
        if os.path.exists(self.__cacheMapPath):
            try:
                self.__cacheMap = pickle.load(open(self.__cacheMapPath, "rb"))
            except Exception:
                logger.log(logging.DEBUG, "failed to load cacheMap file")
        if os.path.exists(self.__cookieMapPath):
            try:
                self.__cookieMapDictionary = pickle.load(open(self.__cookieMapPath, "rb"))
            except Exception:
                logger.log(logging.DEBUG, "failed to load cookie map file")
        self.__initialized = True
    def saveCacheMap(self):
        output = open(self.__cacheMapPath, "wb", -1)
        pickle.dump(self.__cacheMap, output)
        logger.log(logging.DEBUG, "saving cacheMap file: " + self.__cacheMapPath)
    def saveCookieMap(self):
        output = open(self.__cookieMapPath, "wb", -1)
        pickle.dump(self.__cookieMapDictionary, output)
        logger.log(logging.DEBUG, "saving cookieMap file: " + self.__cookieMapPath)

    def getCacheXMLDir(self, urlprefix=None):
        if self.__initialized == False :
            self.loadMaps()
        if urlprefix == None or urlprefix == 'Zone' :
            return self.__cacheParentDir
        cacheDir = None
        try :
            cacheDir = self.__cacheMap[urlprefix]
        except Exception:
            pass
        if cacheDir == None  or cacheDir == '' :
            cacheDir = os.path.join(self.__cacheParentDir, str(int(time.time())))
            self.__cacheMap[urlprefix] = cacheDir
            logger.log(logging.DEBUG, "cacheDir = " + cacheDir)
            self.saveCacheMap()
        if not os.path.exists(cacheDir) :
           try:
              os.mkdir(cacheDir)
           except Exception:
              logger.log(logging.DEBUG, "cache directory already exists")
        return cacheDir
    def getCookieDir(self, url, username):
        if self.__initialized == False :
            self.loadMaps()
        if url == None or url == 'Zone' :
            return self.__cacheParentDir
        cacheDir = None
        hostname = urlparse(url).hostname
        try :
            cookieMapping = self.__cookieMapDictionary[hostname]
            if cookieMapping != None:
                cacheDir = cookieMapping.getCookieDir()
            if (username != None) :
                if (cookieMapping.getUsername() != username):
                    cookieMapping.setUsername(username)
                    self.saveCookieMap()
                    cookieFile = os.path.join(cacheDir, 'cookies.txt')
                    if (os.path.exists(cookieFile)):
                        os.remove(cookieFile)
                        logger.log(logging.DEBUG, "outdated cookie file: " + cookieFile + ' removed')

        except Exception:
            pass
        if cacheDir == None  or cacheDir == '' :
            cacheDir = os.path.join(self.__cacheParentDir, hostname)
            cookieMapping = CookieMap(username, cacheDir)
            self.__cookieMapDictionary[hostname] = cookieMapping
            logger.log(logging.DEBUG, "adding cookieDir: " + cacheDir + ' to cookieMap')
            self.saveCookieMap()
        if not os.path.exists(cacheDir) :
            os.mkdir(cacheDir)
        return cacheDir
    def getCookieFilePath(self, url, username):
        cookies = os.path.join(self.getCookieDir(url, username), "cookies.txt")
        logger.log(logging.DEBUG, "cookie = " + cookies)
        return cookies
    def cleanCache(self, url):
        dir = self.getCacheXMLDir(url)
        if os.path.exists(dir) :
	    try:
               shutil.rmtree(dir)
            except Exception:
               logger.log(logging.DEBUG, "Failed to clean cache")
    def clean(self):
        if options.isClean:
            logger.log(logging.DEBUG, "Recursively remove directory " + self.__cacheParentDir)
            shutil.rmtree(self.__cacheParentDir)
    def findCacheMapDir(self, dir):
        file = self.getCacheMapPath(dir)
        if os.path.exists(file):
            return dir
        else :
            dir = os.path.dirname(dir)
            if dir != None and dir != '/':
                return self.findCacheMapDir(dir)
            else :
                return None
    def getCacheMapPath(self, dir):
        return os.path.join(dir, ".mvl-content", ".cacheMap")

class User:
    def __init__(self, username=None, password=None, uri=None):
        self.__username = username
        if password != None:
            self.__password = base64.b64encode(password)
        self.__uri = uri
        self.__retryCount = 0

    def getRetryCount(self):
        return self.__retryCount
    def setRetryCount(self, value):
        self.__retryCount = value
    def getUsername(self):
        return self.__username
    def getPassword(self):
        try :
            return base64.b64decode(self.__password)
        except TypeError, e:
            sys.stderr.write('Error: Password decode failure - %s\n' % str(e))
            return ""
    def getUri(self):
        return self.__uri
    def setUsername(self, value):
        self.__username = value
    def setPassword(self, value):
        self.__password = base64.b64encode(value)
    def setUri(self, value):
        self.__uri = value
    def createElement(self, dom):
        return dom.createElement("user")
    def toXML(self, dom, element=None):
        if (element == None):
            element = self.createElement(dom)

        element.setAttribute("name", self.getUsername())
        element.setAttribute("password", self.__password)
        element.setAttribute("uri", self.getUri())
        element.setAttribute("retry-count", str(self.getRetryCount()))
        return element
    def fromXML(self, element):
        self.__username = element.attributes["name"].value
        self.__password = element.attributes["password"].value
        self.__uri = element.attributes["uri"].value
        self.__retryCount = int(element.attributes["retry-count"].value)

class PasswordManager:
    """class to store user credential information, deals with username/encrypted password token file
    """
    def __init__(self, logger):
        self.__users = {}
        self.__tokenFilePath = os.path.join(os.path.expanduser('~'), '.mvl-content', '.mvl-user-credential')
        logger.log(logging.DEBUG, "token file path=" + self.__tokenFilePath)

    def addUser(self, user):
        self.__users[user.getUri()] = user
    def removeUser(self, user):
        del self.__users[user.getUri()]
    def findUserByURI(self, uri):
        for k, v in self.__users.iteritems() :
            if uri == k :
                return v
        for k, v in self.__users.iteritems() :
            if self.isSubURI(k, uri) or self.isSubURI(uri, k):
                logger.log(logging.DEBUG, "found user credential from content password manager")
                return v
    def isSubURI(self, item1, item2):
        if item1 == item2 :
            return True
        parsed1 = urlparse(item1)
        parsed2 = urlparse(item2)
        # compare scheme
        if parsed1[0] != parsed2[0]:
            return False;
        # compare netloc
        if parsed1[1] != parsed2[1]:
            return False;
        #compare path
        dir1 = os.path.dirname(parsed1[2])
        dir2 = os.path.dirname(parsed2[2])
        common = os.path.commonprefix((dir1, dir2))
        if len(common) == len(dir1) :
            return True
        return False

    def initialize(self, options):
        if isLocalContentSource(options.uri) == True :
            return
        self.loadToken()

    def loadToken(self):
        """if token file exists, try to load it
        """
        if os.path.exists(self.__tokenFilePath):
            try:
                dom = parse(self.__tokenFilePath)
                rootNodeList = dom.getElementsByTagName("user-credential")
                if rootNodeList.length > 0:
                    rootNode = rootNodeList.item(0)
                    for node in rootNode.getElementsByTagName("user"):
                        user = User()
                        user.fromXML(node)
                        self.addUser(user)
                for v in self.__users.itervalues() :
                    v.setRetryCount(0)
            except Exception:
                logger.log(logging.DEBUG, "failed to load token file")
                #self.deleteTokenFile()
        else:
            self.__users = {}

    def saveToken(self):
        """save the username and encrypted password into token file
        """
        dirname = os.path.dirname(self.__tokenFilePath)
        try :
            if not os.path.exists(dirname) :
                os.makedirs(dirname)
            impl = getDOMImplementation()
            dom = impl.createDocument(None, "user-credential", None)
            top_element = dom.documentElement
            for user in self.__users.itervalues() :
                element = user.toXML(dom)
                top_element.appendChild(element)

            output = open(self.__tokenFilePath, "wb", -1)
            output.write(pretty_print(dom))
            os.chmod(self.__tokenFilePath, 0600)
            logger.log(logging.DEBUG, "saving token to file: " + self.__tokenFilePath)
        except EnvironmentError, e:
            sys.stderr.write('Error: [Errno ' + str(e.errno) + '] ')
            sys.stderr.write(str(e.strerror))
            if e.filename != None:
                sys.stderr.write(' ' + str(e.filename))
            sys.stderr.write('\n')
            logger.log(logging.WARNING, 'user credential not saved. You might need to re-supply username/password again.')
    def deleteTokenFile(self):
        self.__users = {}
        fileExists = os.path.exists(self.__tokenFilePath)
        if fileExists :
            os.remove(self.__tokenFilePath)
            logger.log(logging.DEBUG, 'removing token file: ' + self.__tokenFilePath)

supported_schemes = ('http', 'https', 'ftp','ssh')

def isLocalContentSource(uri):
    #return true for file:/// scheme
    parsed = urlparse(uri)
    if parsed[0] == 'file' :
        return True
    return False
def isSupportedRemotecontentSource(uri):
    parsed = urlparse(uri)
    scheme = parsed[0]
    if scheme.lower() in supported_schemes:
        return True
    else :
        return False
def getCookiesFilePath(url, username):
    return contentCache.getCookieFilePath(url, username)
def getDefaultContentCacheDir(url):
    return contentCache.getCacheXMLDir(url)
def getReturnStatus(output):
    errCode = None
    lines = output.splitlines()
    for line in lines:
        line = line.lstrip()
        if line.startswith("HTTP/1.") :
            substrings = line.split()
            # substring should be like: ['HTTP/1.1', '401', 'Authorization', 'Required']
            if len(substrings) > 1 :
                errCode = substrings[1]
                logger.log(logging.DEBUG, 'HTTP Return Code: ' + errCode)

    if errCode == None :
        errCode = output
    return errCode
def downloadFileUsingURLLib(url, workingdir=os.getcwd(), dirPrefix=None, verbose=False, timeout=60, destFile=None):
    global logger
    global passwordManager
    global currentDownloadRetryCount
    import errno

    if currentDownloadRetryCount <= 0 :
        sys.stderr.write('Error: reaching maximum retry for downloading.\nExiting.\n')
        logger.log(logging.DEBUG, 'program exists with error code 1\n')
        sys.exit(1)
    else :
        currentDownloadRetryCount = currentDownloadRetryCount - 1
    user = getUserFromPasswordManager(logger)
    username = options.username
    if (user != None) :
        username = user.getUsername()
    cookiesFilePath = getCookiesFilePath(url, username)
    if options.cookie:
       print cookiesFilePath
       sys.exit(0)
    logger.log(logging.DEBUG, 'Starting downloading file using urllib2')
    logger.log(logging.DEBUG, 'url=' + url)
    logger.log(logging.DEBUG, 'workingdir=' + workingdir)
    if dirPrefix != None :
        logger.log(logging.DEBUG, 'dirPrefix=' + dirPrefix)
    try :
        cj = cookielib.MozillaCookieJar()
        if os.path.exists(cookiesFilePath) :
            cj.load(cookiesFilePath)
    except cookielib.LoadError:
        cj = cookielib.LWPCookieJar()
        try :
            if os.path.exists(cookiesFilePath) :
                cj.load(cookiesFilePath)
        except cookielib.LoadError:
            pass
    opener = None
    
   
    scheme, sel_url = urllib.splittype(url)
    if scheme.lower() == 'ftp':
        import re
        valid_ftp_url = re.compile('^ftp://([A-Za-z0-9_-]+:[A-Za-z0-9_-]+@)?(.*)$')
        match_valid_ftp = valid_ftp_url.match(url)
        invalid_ftp_msg = "Invalid ftp url: %s. Expected: ftp://[user:password@]host/path_to_file" % url
        if match_valid_ftp is None:
            raise Exception(invalid_ftp_msg)

        url_without_scheme = sel_url[2:]
        if sel_url is None:
            raise Exception(invalid_ftp_msg)

        sel_host, sel_path = splithost(sel_url)
        
        if sel_host is None:
            raise Exception(invalid_ftp_msg)

        sel_user, host = splituser(sel_host)
        
        if not sel_user is None:
            sel_user, sel_password = splitpasswd(sel_user)
            
            if not sel_user is None and len(sel_user) > 0 and not sel_password is None and len(sel_password) > 0:
                # reconstruct url
                url = "ftp://%s:%s@%s%s" % (sel_user, sel_password, host, sel_path)
                if user == None:
                    user = User(sel_user, sel_password, url)
                    logger.log(logging.DEBUG, 'Adding user: ' + user.getUsername() + ' into content password manager')
                else:
                    user.setUsername(sel_user)
                    user.setPassword(sel_password)
                    logger.log(logging.DEBUG, 'Updating user credential for: ' + user.getUsername() + ' in content password manager')

        
        else:
            if not user is None:
                url = "ftp://%s:%s@%s%s" % (user.getUsername(), user.getPassword(), host, sel_path)        
               
        
    if user != None:
        user.setRetryCount(user.getRetryCount() + 1)
        passman = urllib2.HTTPPasswordMgrWithDefaultRealm()
        passman.add_password(None, url, user.getUsername(), user.getPassword())
        authhandler = urllib2.HTTPBasicAuthHandler(passman)
        opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cj), authhandler)
    else :
        opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cj))

    r = None
    localFile = None
    try:
        if verbose :
            print '\tfetching ' + url + '...'
        # timeout after 60 seconds of blocking operations like the connection attempt
        r = opener.open(url, timeout=timeout)
        if hasattr(options, 'checkuri') and options.checkuri:
           if r.code == 200:
              sys.exit(0)
        if not destFile:
           filename = url.split('/')[-1]
        else:
           filename = destFile
        if filename.strip() == '' :
            sys.stderr.write('Error: URI does not contain the filename for downloading.\nExiting.\n')
            logger.log(logging.DEBUG, 'program exists with error code 1\n')
            sys.exit(1)
        if dirPrefix != None :
            filenamePath = os.path.join(workingdir, dirPrefix, filename)
        else :
            filenamePath = os.path.join(workingdir, filename)
        filenamePath = os.path.abspath(filenamePath)
        logger.log(logging.DEBUG, 'downloading file to ' + filenamePath)
        dirname = os.path.dirname(filenamePath)
        if not os.path.exists(dirname) :
            os.makedirs(dirname)
        localFile = open(filenamePath, 'w')
        localFile.write(r.read())
        cj.save(cookiesFilePath)
        return filenamePath
    except urllib2.HTTPError, e :
        if hasattr(options, 'checkuri') and options.checkuri:
           sys.exit(1)
        if hasattr(e, 'code') and e.code == 401 :
            if user != None and user.getUri() == url :
                sys.stderr.write('Error: Invalid username and password combination for: ' + url + '\n')
                if user.getRetryCount() > 3 :
                    sys.stderr.write('Error: Max authentication retry count reached.\nExiting.\n')
                    logger.log(logging.DEBUG, 'program exists with error code 2\n')
                    sys.exit(2)
            if (hasattr(options, 'noninteractive') and options.noninteractive):
                sys.stderr.write('Error: Authentication failed. Exiting.\n')
                logger.log(logging.DEBUG, 'program exists with error code 2\n')
                sys.exit(2)
            else :
                username = raw_input('Please enter username: ')
                password = getpass.getpass('Please enter password: ')
                options.username = None
                options.password = None
                if user == None or user.getUri() != url :
                    user = User(username, password, url)
                    logger.log(logging.DEBUG, 'Adding user: ' + user.getUsername() + ' into content password manager')
                    passwordManager.addUser(user)
                else :
                    user.setUsername(username)
                    user.setPassword(password)
                    logger.log(logging.DEBUG, 'Updating user: ' + user.getUsername() + ' in content password manager')
                passwordManager.saveToken()
                return downloadFileUsingURLLib(url, workingdir, dirPrefix, verbose, timeout, destFile)


        else :
            if e.code != 404 or (hasattr(options, 'missingok') and not options.missingok and e.code == 404) :
                sys.stderr.write('Receive HTTP Error for: ' + url + '\n')
                if hasattr(e, 'code') :
                    sys.stderr.write('error code: ' + str(e.code) + '\n')
                if hasattr(e, 'msg') :
                    sys.stderr.write('error message: ' + str(e.msg) + '\n')
                if hasattr(e, 'reason') :
                    sys.stderr.write('error reason: ' + (e.reason) + '\n')
                sys.stderr.write('Exiting.\n')
                logger.log(logging.DEBUG, 'program exists with error code 3\n')
                sys.exit(3)
            elif e.code == 404 and (hasattr(options, 'missingok') and options.missingok) and verbose:
                logger.log(logging.WARNING, 'Failed to download file. File not found ' + url)

    except urllib2.URLError, e :
        sys.stderr.write('URL Error: ')
        if hasattr(e, 'code') :
            sys.stderr.write(str(e.code) + '\n')
        if hasattr(e, 'msg') :
            sys.stderr.write(str(e.msg) + '\n')
        if hasattr(e, 'reason') :
            sys.stderr.write(str(e.reason) + '\n')
            # if connection reset by peer or timeout
            if str(e.reason).find('Connection reset by peer') != -1 or str(e.reason).find('The read operation timed out') != -1 :
                sys.stderr.write('Retrying download. URI: ' + url + '...\n')
                return downloadFileUsingURLLib(url, workingdir, dirPrefix, verbose, timeout, destFile)
        sys.stderr.write('Exiting.\n')
        logger.log(logging.DEBUG, 'program exists with error code 3\n')
        sys.exit(3)
    except ValueError, e :
        exc_type, exc_value, exc_traceback = sys.exc_info()
        sys.stderr.write(str(exc_type) + ', ' + str(exc_value) + '\n')
        if hasattr(e, 'args') :
            sys.stderr.write('args: ' + str(e.args) + '\n')
        logger.log(logging.DEBUG, 'program exists with error code 1\n')
        sys.exit(1)
    except socket.timeout :
        sys.stderr.write('socket timeout\n')
        sys.stderr.write('Retrying download URI: ' + url + '...\n')
        return downloadFileUsingURLLib(url, workingdir, dirPrefix, verbose, timeout, destFile)
    except socket.error, e :
        sys.stderr.write('socket.error: (' + str(e) + ')\n')
        sys.stderr.write('Retrying download. URI: ' + url + '...\n')
        return downloadFileUsingURLLib(url, workingdir, dirPrefix, verbose, timeout, destFile)
    except IOError, e :
        parsed = urlparse(url)
        srcname = parsed[2]
        if e.errno == errno.EFBIG and (hasattr(options, 'missingok') and options.missingok):
            return None
        sys.stderr.write('IO Error: ')
        sys.stderr.write(str(e.strerror) + ' ' + srcname)
        sys.stderr.write('\nExiting.\n')
        logger.log(logging.DEBUG, 'program exists with error code 1\n')
        sys.exit(1)
    finally:
        if r != None :
            r.close()
        if localFile != None :
            localFile.close()

    return None
def downloadFile(url, workingDir=os.getcwd(), dirPrefix=None, options=None, verbose=False, collectionUri=None, bare=True, useGit=False, destFile=None):
    global maxDownloadRetryCount
    global currentDownloadRetryCount

    isSupportedRemoteContentSource = isSupportedRemotecontentSource(url)
    if not options:
        timeout = 60
    else:
        timeout = options.defaulttimeout
    if isSupportedRemoteContentSource and not useGit:
        #reset currentDownloadRetryCount
        currentDownloadRetryCount = maxDownloadRetryCount
        if url.startswith("ssh"):
           return downloadFileUsingSsh(url, workingDir, dirPrefix, verbose, timeout)
        if options != None and options.wget :
            return downloadFileUsingWget(url, workingDir, dirPrefix, verbose, timeout, destFile)
        else :
	    try:
               return downloadFileUsingURLLib(url, workingDir, dirPrefix, verbose, timeout, destFile)
	    except MemoryError:
	       return downloadFileUsingWget(url, workingDir, dirPrefix, verbose, timeout, destFile)
    else :
        if url == '' :
            sys.stderr.write('\nError: Empty URI specified.\n')
            sys.stderr.write('Exiting.\n')
            logger.log(logging.DEBUG, 'program exists with error code 1\n')
            sys.exit(1)
        if url.startswith("git://") or useGit:
           user = getUserFromPasswordManager(logger)
           username = options.username
           if (user != None) :
              username = user.getUsername()
           if not collectionUri.startswith("file://"):
              cookiesFilePath = getCookiesFilePath(collectionUri, username)
           else:
              cookiesFilePath = None
           gitCheckoutUpdate(url, workingDir, bare, collectionUri, options,cookieFile=cookiesFilePath)
        elif isLocalContentSource(url):
            parsed = urlparse(url)
            srcname = parsed[2]
            if dirPrefix == None:
                dstname = workingDir
            else :
                dstname = os.path.join(workingDir, dirPrefix)
            if verbose :
                print '\tcopying ' + srcname + '...'

            try :
                if hasattr(options, 'missingok') and options.missingok :
                    if not os.path.exists(srcname):
                        if verbose:
                            logger.log(logging.WARNING, 'Failed to download file. No such file or directory ' + srcname)
                        return None
                exists = os.path.exists(dstname)
                if not exists :
                    os.makedirs(dstname)
                shutil.copy(srcname, dstname)
                logger.log(logging.DEBUG, 'copy to: ' + dstname)
                filename = os.path.basename(srcname)
                return os.path.join(dstname, filename)
            except IOError, e :
                sys.stderr.write('IO Error: ')
                sys.stderr.write(str(e.strerror) + ' ' + srcname)
                sys.stderr.write('\nExiting.\n')
                logger.log(logging.DEBUG, 'program exists with error code 1\n')
                sys.exit(1)
        else :
            sys.stderr.write('Warning: Invalid url syntax for download : ' + url + '\n')

def downloadFileUsingSsh(url, workingdir, dirPrefix=None, verbose=False, timeout=60):
    global currentDownloadRetryCount
    global maxDownloadRetryCount
    logger.log(logging.DEBUG, 'Starting downloading file using ssh')
    options=url.split(';')
    urlsplit = url.split('/')
    downloadDir = os.path.abspath("/".join([workingdir,dirPrefix or ""]))
    sshArgs= [ 'scp', urlsplit[2]+ ":/" + "/".join(urlsplit[3:]), downloadDir]
    if not os.path.isdir(downloadDir):
       os.makedirs(downloadDir)
    if verbose:
       print '\tfetching ' + url + '...'
    p = subprocess.Popen(sshArgs, cwd=workingdir, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (stdoutdata, stderrdata) = p.communicate()
    retcode = p.returncode
    logger.log(logging.DEBUG, 'return code for download = ' + str(retcode))
    if retcode != 0:
          return None
    return os.path.join(downloadDir, urlsplit[-1])

def downloadFileUsingWget(url, workingdir, dirPrefix=None, verbose=False, timeout=60, destFile=None):
    global currentDownloadRetryCount
    global maxDownloadRetryCount

    logger.log(logging.DEBUG, 'Starting downloading file using wget')

    if currentDownloadRetryCount <= 0 :
        sys.stderr.write('Error: reaching maximum retry for downloading.\nExiting.\n')
        logger.log(logging.DEBUG, 'program exists with error code 1\n')
        sys.exit(1)
    else :
        currentDownloadRetryCount = currentDownloadRetryCount - 1
    logger.log(logging.DEBUG, 'url=' + url)
    logger.log(logging.DEBUG, 'workingdir=' + workingdir)
    if dirPrefix != None :
        logger.log(logging.DEBUG, 'dirPrefix=' + dirPrefix)
    if destFile == None:
       filename = url.split('/')[-1]
    else:
       filename = destFile
    if filename.strip() == '' :
        sys.stderr.write('Error: URI does not contain the filename for downloading.\nExiting.\n')
        logger.log(logging.DEBUG, 'program exists with error code 1\n')
        sys.exit(1)
    user = getUserFromPasswordManager(logger)
    username = options.username
    if (user != None) :
        username = user.getUsername()
    cookiesFilePath = getCookiesFilePath(url, username)
    if os.path.exists(cookiesFilePath):
        #printCookies(cookiesFilePath)
        cookieArgs = [ '--cookies=on', '--load-cookies' , cookiesFilePath]
    else:
        cookieArgs = []

    if user != None:
        userArgs = [ '--http-user', user.getUsername() , '--http-password' , user.getPassword(), '--save-cookies', cookiesFilePath ]
        user.setRetryCount(user.getRetryCount() + 1)
    else :
        userArgs = []
    logger.log(logging.DEBUG, 'downloading: %s' % url)
    checkuriflag = ""
    if hasattr(options, 'checkuri') and options.checkuri:
       checkuriflag=" --spider "
    if destFile:
       outputArgs = ['-O', destFile]
    else:
       outputArgs = []
    if verbose:
        print '\tfetching ' + url + '...'
    wgetArgs = ['wget', checkuriflag, '-S', '-m', '-nd', '--no-check-certificate', '--continue', '--dot-style=mega', '--retry-connrefused', '--tries', str(maxDownloadRetryCount), '--timeout', str(timeout)] + outputArgs + userArgs + cookieArgs + [ url]
    if dirPrefix != None :
        wgetArgs.insert(1, '--directory-prefix=' + dirPrefix)
    logger.log(logging.DEBUG, 'wget-args: %s' % wgetArgs)
    p = subprocess.Popen(wgetArgs, cwd=workingdir, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (stdoutdata, stderrdata) = p.communicate()
    retcode = p.returncode
    downloadSuccessful = False
    logger.log(logging.DEBUG, 'return code for download = ' + str(retcode))
    if retcode != 0 or (stderrdata != None and len(stderrdata) > 0):
        code = getReturnStatus(stderrdata)
        if hasattr(options, 'checkuri') and options.checkuri:
           if code == '200':
              sys.exit(0)
           else:
              sys.exit(1)
        if code == '200':
            downloadSuccessful = True
            logger.log(logging.DEBUG, 'download successful\n')
        elif code.isdigit() and int(code) > 200 and int(code) < 300 :
            downloadSuccessful = True
            logger.log(logging.WARNING, 'HTTP return code: ' + code)
        elif code == '416' :
            downloadSuccessful = True
        elif code == '401' :
            if user != None and user.getUri() == url :
                sys.stderr.write('Error: Invalid username and password combination for: ' + url + '\n')
                if user.getRetryCount() > 3 :
                    sys.stderr.write('Error: Max authentication retry count reached.\nExiting.\n')
                    logger.log(logging.DEBUG, 'program exists with error code 2\n')
                    sys.exit(2)
            if hasattr(options, 'noninteractive') and options.noninteractive :
                sys.stderr.write('Error: Authentication failed. Exiting.\n')
                logger.log(logging.DEBUG, 'program exists with error code 2\n')
                sys.exit(2)
            else :
                username = raw_input('Please enter username: ')
                password = getpass.getpass('Please enter password: ')
                options.username = None
                options.password = None
                if user == None or user.getUri() != url :
                    user = User(username, password, url)
                    logger.log(logging.DEBUG, 'Adding user: ' + user.getUsername() + ' into content password manager')
                    passwordManager.addUser(user)
                else :
                    user.setUsername(username)
                    user.setPassword(password)
                    logger.log(logging.DEBUG, 'Updating user: ' + user.getUsername() + ' in content password manager')
                passwordManager.saveToken()
                return downloadFileUsingWget(url, workingdir, dirPrefix, timeout, destFile)
        else :
            if code != '404' or ((hasattr(options, 'missingok') and code == '404' and not options.missingok)) :
                sys.stderr.write('Error: download failed with code = ' + str(code) + '\n')
                sys.stderr.write('Exiting.\n')
                logger.log(logging.DEBUG, 'program exists with error code 3\n')
                sys.exit(3)
            elif code == '404' and (hasattr(options, 'missingok') and options.missingok) and verbose:
                logger.log(logging.WARNING, 'Failed to download file. File not found ' + url)
            elif code.isdigit() :
                errorno = int(code)
                if errorno >= 100 and errorno <= 510 :
                    logger.log(logging.WARNING, 'HTTP return code: ' + code)
            else :
                logger.log(logging.WARNING, 'HTTP return code: ' + code)
                sys.stderr.write('Retrying download. URI: ' + url + '...\n')
                return downloadFileUsingWget(url, workingdir, dirPrefix, timeout, destFile)

    else :
        downloadSuccessful = True
    if downloadSuccessful :
        if dirPrefix != None :
            filenamePath = os.path.join(workingdir, dirPrefix, filename)
        else :
            filenamePath = os.path.join(workingdir, filename)
        filenamePath = os.path.abspath(filenamePath)
        logger.log(logging.DEBUG, 'downloading file to ' + filenamePath)

        if stdoutdata != None and stdoutdata.strip() != '':
            print stdoutdata
        if stderrdata != None and stderrdata.strip() != '' :
            print stderrdata
        return filenamePath

def removeUserFromPasswordManager(user, logger):
    global passwordManager
    if passwordManager == None:
       return
    passwordManager.removeUser(user)
    passwordManager.saveToken()
def getUserFromPasswordManager(logger):
    global passwordManager
    if  not isLocalContentSource(options.uri):
        if passwordManager == None :
            passwordManager = PasswordManager(logger)
            passwordManager.initialize(options)
        """
        find user and password from password manager, if there is a uri with the same base in password manager
        retrieve that user and return
        """
        if options.uri != None:
            user = passwordManager.findUserByURI(options.uri)
            if user != None :
                if options.username == None and options.password == None:
                    return user
                if options.password == None:
                    return user
                if options.username == user.getUsername() and options.password == user.getPassword() :
                    return user
            
            if options.username != None and options.password != None and options.uri != None :
                user = User(options.username, options.password, options.uri)
                passwordManager.addUser(user)
                logger.log(logging.DEBUG, 'Adding user: ' + user.getUsername() + ' into content password manager')
                passwordManager.saveToken()
                return user
    return None
class ContentTools(object):
    def __init__(self, inputOptions):
        global options
        global contentCache
        global passwordManager
        global logger
        global maxDownloadRetryCount
        global currentDownloadRetryCount
        options = inputOptions
        logger = logging.getLogger("ContentTools")
        self.initializeLogger(logger)

        contentCache = ContentCache()
        self.initContentSource()
        passwordManager = PasswordManager(logger)
        passwordManager.initialize(options)
        maxDownloadRetryCount = 5
        currentDownloadRetryCount = maxDownloadRetryCount

    def getLogger(self):
        return self.logger
    def initializeLogger(self, logger):
        #create console handler
        ch = logging.StreamHandler()
        #create formatter
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        #add formatter to ch
        ch.setFormatter(formatter)
        #add ch to logger
        logger.addHandler(ch)

        if options.isDebug:
            logger.log(logging.DEBUG, 'Running in Debug Mode')
            logger.setLevel(logging.DEBUG)
            ch.setLevel(logging.DEBUG)
        else:
            logger.setLevel(logging.INFO)
            ch.setLevel(logging.INFO)
    def getDefaultContentSourceConfigPath(self):
        currentPath = os.path.dirname(__file__)
        logger.log(logging.DEBUG, 'ContentTools module path: ' + currentPath)
        if currentPath != None :
            libPath = os.path.dirname(currentPath)
            if libPath != None :
                ipPath = os.path.dirname(libPath)
                if ipPath != None :
                    return os.path.join(ipPath, 'etc', 'ContentSource.properties')
        return None

    def initContentSource(self):
        if options.uri == None:
            finalDefaultURI = "https://support.mvista.com/cgx2.2/site.xml"
            defaultContentSourceConfigPath = self.getDefaultContentSourceConfigPath()
            logger.log(logging.DEBUG, 'Content Source configuration path: ' + str(defaultContentSourceConfigPath))

            if defaultContentSourceConfigPath != None and os.path.exists(defaultContentSourceConfigPath):
                configParser = ConfigParser()
                configParser.read(defaultContentSourceConfigPath)
                try:
                    defaultURI = configParser.get("Content Source", "uri")
                    options.uri = defaultURI
                    logger.log(logging.DEBUG, 'setting default uri from content source configuration file')
                except Exception, e:
                    print 'Warning: unable to get default content source from configuration file:', defaultContentSourceConfigPath
                    print str(e)
                    print 'Setting to default Content Source' , finalDefaultURI


        if options.uri == None:
            options.uri = finalDefaultURI
    def getContentSource(self):
        return options.uri

    def downloadFile(self, url, workingDir=os.getcwd(), dirPrefix=None, options=None, verbose=False, collectionUri=None,bare=True, useGit=False, destFile=None):
        return downloadFile(url, workingDir, dirPrefix, options, verbose, collectionUri, bare, useGit, destFile)
    def getLocalContentObject(self, filepath):
        logger.log(logging.DEBUG, 'Getting Local Content Object from: ' + filepath)
        if filepath != None :
            try :
                dom = parse(filepath)
                contentObj = self.contentObjectFactory(dom)
                return contentObj
            except ExpatError, e:
                sys.stderr.write('\nError: XML Parsing Exception\n')
                sys.stderr.write('Error: ' + str(e) + '\n')
        return None
    def getContentObject(self, url, dirPrefix=None):
        workingDir = getDefaultContentCacheDir(url)
        logger.log(logging.DEBUG, 'Getting Content Object with specified url: ' + url)
        filepath = self.downloadFile(url, workingDir, dirPrefix, verbose=False, options=options)
        if filepath != None :
            try :
                dom = parse(filepath)
                contentObj = self.contentObjectFactory(dom)
                contentCache.cleanCache(url)
                return contentObj
            except ExpatError, e:
                sys.stderr.write('\nError: XML Parsing Exception\n')
                sys.stderr.write('Error: ' + str(e) + '\n')

        return None
    def contentObjectFactory(self, dom):
        logger.log(logging.DEBUG, 'Getting Content Object using Content Object Factory')
        rootChildNode = dom.childNodes[0]
        rootElementName = rootChildNode.nodeName
	runApp=(os.path.basename(sys.argv[0]))
        if rootElementName == 'site' :
            site = Site()
            site.fromXML(dom)
            logger.log(logging.DEBUG, 'Returing Site object from Content Object Factory')
            return site
        elif rootElementName == 'collection' and runApp != "mvl-image-project":
            collection = Collection()
            collection.fromXML(rootChildNode)
            logger.log(logging.DEBUG, 'Returing Collection object from Content Object Factory')
            return collection
        elif rootElementName == 'solution' :
            solution = Solution()
            solution.fromXML(rootChildNode)
            logger.log(logging.DEBUG, 'Returing Solution object from Content Object Factory')
            return solution
        elif rootElementName == 'collection-manifest' and runApp != "mvl-image-project":
            collectionManifest = CollectionManifest()
            collectionManifest.fromXML(rootChildNode)
            logger.log(logging.DEBUG, 'Returing Collection Manifest object from Content Object Factory')
            return collectionManifest
        elif rootElementName == 'solution-manifest' :
            solutionManifest = SolutionManifest()
            solutionManifest.fromXML(rootChildNode)
            logger.log(logging.DEBUG, 'Returing Solution Manifest object from Content Object Factory')
            return solutionManifest
        logger.log(logging.DEBUG, 'Unable to create object from Content Object Factory')
        return None


# Main program
if __name__ == '__main__':

    #create cmd options parser
    usage = "usage: ContentTools [options] "
    parser = OptionParser(usage=usage, version="%prog 2.2.0.180327151823")
    cmdOptions = CmdOptions()
    cmdOptions.configureOptionParser()

    #parse cmd arguments
    (options, args) = parser.parse_args()
    contentTools = ContentTools(options)
    logger = contentTools.getLogger()

