/**
 * KaspaQuest WebSocket Server
 * Modernized version using 'ws' package
 */

var cls = require("./lib/class"),
    url = require('url'),
    http = require('http'),
    WebSocket = require('ws'),
    Utils = require('./utils'),
    _ = require('underscore'),
    WS = {};

module.exports = WS;

/**
 * Abstract Server and Connection classes
 */
var Server = cls.Class.extend({
    init: function(port) {
        this.port = port;
    },
    
    onConnect: function(callback) {
        this.connection_callback = callback;
    },
    
    onError: function(callback) {
        this.error_callback = callback;
    },
    
    broadcast: function(message) {
        throw "Not implemented";
    },
    
    forEachConnection: function(callback) {
        _.each(this._connections, callback);
    },
    
    addConnection: function(connection) {
        this._connections[connection.id] = connection;
    },
    
    removeConnection: function(id) {
        delete this._connections[id];
    },
    
    getConnection: function(id) {
        return this._connections[id];
    }
});

var Connection = cls.Class.extend({
    init: function(id, connection, server) {
        this._connection = connection;
        this._server = server;
        this.id = id;
    },
    
    onClose: function(callback) {
        this.close_callback = callback;
    },
    
    listen: function(callback) {
        this.listen_callback = callback;
    },
    
    broadcast: function(message) {
        throw "Not implemented";
    },
    
    send: function(message) {
        throw "Not implemented";
    },
    
    sendUTF8: function(data) {
        throw "Not implemented";
    },
    
    close: function(logError) {
        log.info("Closing connection to " + this._connection._socket.remoteAddress + ". Error: " + logError);
        this._connection.close();
    }
});

/**
 * Modern WebSocket Server using 'ws' package
 */
WS.MultiVersionWebsocketServer = Server.extend({
    _connections: {},
    _counter: 0,
    
    init: function(port) {
        var self = this;
        
        this._super(port);
        
        // Create HTTP server for status endpoint
        this._httpServer = http.createServer(function(request, response) {
            var path = url.parse(request.url).pathname;
            switch(path) {
                case '/status':
                    if(self.status_callback) {
                        response.writeHead(200, {'Content-Type': 'application/json'});
                        response.write(self.status_callback());
                        break;
                    }
                default:
                    response.writeHead(404);
            }
            response.end();
        });
        
        // Create WebSocket server
        this._wsServer = new WebSocket.Server({ server: this._httpServer });
        
        this._wsServer.on('connection', function(ws, req) {
            // Add remoteAddress
            ws.remoteAddress = req.socket.remoteAddress;
            
            var c = new WS.ModernWebSocketConnection(self._createId(), ws, self);
            
            if(self.connection_callback) {
                self.connection_callback(c);
            }
            self.addConnection(c);
        });
        
        this._wsServer.on('error', function(error) {
            if(self.error_callback) {
                self.error_callback(error);
            }
        });
        
        this._httpServer.listen(port, function() {
            log.info("Server is listening on port " + port);
        });
    },
    
    _createId: function() {
        return '5' + Utils.random(99) + '' + (this._counter++);
    },
    
    broadcast: function(message) {
        this.forEachConnection(function(connection) {
            connection.send(message);
        });
    },
    
    onRequestStatus: function(status_callback) {
        this.status_callback = status_callback;
    }
});

/**
 * Modern WebSocket Connection using 'ws' package
 */
WS.ModernWebSocketConnection = Connection.extend({
    init: function(id, connection, server) {
        var self = this;
        
        this._super(id, connection, server);
        
        this._connection.on('message', function(data) {
            if(self.listen_callback) {
                try {
                    // Handle both Buffer and string
                    var message = data.toString();
                    self.listen_callback(JSON.parse(message));
                } catch(e) {
                    if(e instanceof SyntaxError) {
                        self.close("Received message was not valid JSON.");
                    } else {
                        throw e;
                    }
                }
            }
        });
        
        this._connection.on('close', function() {
            if(self.close_callback) {
                self.close_callback();
            }
            self._server.removeConnection(self.id);
        });
        
        this._connection.on('error', function(error) {
            log.error("WebSocket error: " + error);
        });
    },
    
    send: function(message) {
        var data = JSON.stringify(message);
        this.sendUTF8(data);
    },
    
    sendUTF8: function(data) {
        if(this._connection.readyState === WebSocket.OPEN) {
            this._connection.send(data);
        }
    }
});

// Export for backwards compatibility
WS.worlizeWebSocketConnection = WS.ModernWebSocketConnection;
WS.miksagoWebSocketConnection = WS.ModernWebSocketConnection;
