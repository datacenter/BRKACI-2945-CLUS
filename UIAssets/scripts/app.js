window.LOCAL = window.location['host'].indexOf('localhost') !== -1;

if (!window.LOCAL) {
    window.ADDRESS = window.location['host'];
    window.ENTRY_POINT = window.location['host'];
    window.TOKEN = Ext.util.Cookies.get('app_Cisco_CLUS_token');
    window.URL_TOKEN = Ext.util.Cookies.get('app_Cisco_CLUS_urlToken');
    window.BACKEND_QUERY_URL = 'https://' + window.ADDRESS + '/appcenter/Cisco/CLUS';
    window.addEventListener('message', function (e) {
        if (e.source === window.parent) {
            var tokenObj = Ext.decode(e.data, true);
            if (tokenObj) {
                window.APIC_DEV_COOKIE = tokenObj.token;
                window.APIC_URL_TOKEN = tokenObj.urlToken;
                Ext.util.Cookies.set('app_Cisco_CLUS_token', tokenObj.token);
                Ext.util.Cookies.set('app_Cisco_CLUS_urlToken', tokenObj.urlToken);
            }
        }
    });
} else {
    window.ADDRESS = 'bdsol-aci19-apic1.cisco.com';
}
window.ENTRY_POINT = 'https://' + window.ADDRESS;

function openSession(callback) {
    console.log('Opening session to ' + window.ADDRESS);
    $.ajax({
        type: 'POST',
        url: window.ENTRY_POINT + '/api/aaaLogin.json?gui-token-request=yes',
        dataType: 'json',
        success: function (results) {
            callback(results.imdata[0].aaaLogin.attributes);
        },
        error: function (responseData, textStatus, errorThrown) {
            console.error(responseData);
        },
        data: JSON.stringify({
            'aaaUser': {
                'attributes': {
                    'name': 'admin',
                    'pwd': 'ins3965!'
                }
            }
        })
    });
}

function getFromApi(url, success, error) {
    var params = {
        type: 'GET',
        url: window.ENTRY_POINT + url,
        dataType: 'json',
        headers: {
            'DevCookie': window.TOKEN
        },
        success: function (results) {
            success(results)
        },
        error: function (results) {
            error(results)
        }
    };
    if (window.LOCAL) {
        console.log('Getting local url ' + url);
        params['data'] = 'challenge=' + window.URL_TOKEN;
    } else {
        console.log('Getting app url ' + url);
        params['headers']['APIC-challenge'] = window.APIC_URL_TOKEN;
    }
    $.ajax(params);
}

function listEndpoints(subnet, success, error) {
    console.log('Listing endpoints');
    getFromApi('/api/class/fvCEp.json?query-target-filter=wcard(fvCEp.ip,"' + subnet + '")&rsp-subtree=children', success, error);
}

function resolveIp(ip, success, error) {
    console.log('Resolving IP ' + ip);
    getFromApi('/appcenter/Cisco/CLUS/resolve.json?ip=' + ip, success, error);
}

$(function () {
    console.log('Frontend is ready');
    if (window.LOCAL) {
        openSession(function (aaaLoginAttributes) {
            console.log('Session is ready');
            window.TOKEN = aaaLoginAttributes.token;
            window.URL_TOKEN = aaaLoginAttributes.urlToken;
        });
    }
    $(document).on('click', '.resolve', function (event) {
        event.preventDefault();
        var ip = $(this).attr('id');
        resolveIp(ip, function (results) {
            if ("ptr" in results ) {
                console.log(results);
                if (results["ptr"] == "n/a") {
                    $('tbody td:contains(' + ip + ')').text(ip + " (n/a)");
                } else { 
                    $('tbody td:contains(' + ip + ')').text(results['ptr']);
                }
            } else {
                console.error(results);
            }
        }, function (error) {
            console.error(error);
        })
    });
    $('form').submit(function (event) {
        event.preventDefault();
        var subnet = $('#subnet').val();
        listEndpoints(subnet, function (results) {
            var entries = results['imdata'];
            var tbody = $('tbody');
            tbody.empty();
            for (var i = 0; i < entries.length; i++) {
                var attributes = entries[i]['fvCEp'].attributes;
                var ip = attributes['ip'];
                var mac = attributes['mac'];
                var encap = attributes['encap'];
                var line = '<td>' + ip + '</td><td>' + mac + '</td><td>' + encap + '</td><td><a href="#" id="' + ip + '" class="resolve icon-language icon-medium"></a></td>';
                tbody.append('<tr>' + line + '</tr>');
            }
        }, function (error) {
            console.error(error);
        });
    });
});
