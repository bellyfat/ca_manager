#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from peewee import *

import os
import os.path

from paths import *

__doc__= """
Module of classes to handle certificate requests
"""

class Authority(object):
    request_allowed = []

    def __init__(self, ca_id, ca_dir = MANAGER_PATH):
        self.ca_id = ca_id
        self.ca_dir = ca_dir

    def __bool__(self):
        return os.path.exists(self.path)

    @property
    def path(self):
        return os.path.join(self.ca_dir, self.ca_id)

    def generate(self):
        """
        Leave a dump of this class in the MANAGER_PATH
        """
        pickled_path = os.path.join(MANAGER_PATH, 'pickled_cas', self.ca_id)
        with open(pickled_path, 'wb') as out:
                pickle.dump(self, out)

    def sign(self, request):
        raise NotImplementedError()

    def __repr__(self):
        return ( "%s %s" % ( self.__class__.__name__, self.ca_id ) )

class SSHAuthority(Authority):

    request_allowed = [ UserSSHRequest, HostSSHRequest, ]

    key_algorithm = 'ed25519'

    user_validity = '+52w'
    host_validity = '+52w'

    def __init__(self, ca_id):
        ssh_ca_dir = os.path.join(MANAGER_PATH, 'ssh_cas')

        super(SSHAuthority, self).__init__(ca_id, ssh_ca_dir)

    def __bool__(self):
        """
        For a SSH Authority we only need a private-public key couple,
        moreover we request to have the next serial number
        """
        keys_couple_exist = os.path.exists(self.path) and os.path.exists(self.path + '.pub')
        serial_exist = os.path.exists(self.path + '.serial')

        return keys_couple_exist and serial_exist

    def generate(self):
        """
        Generate a SSHAuthority if the files associated
        do not exists
        """
        # check if the public key exists
        if not self:
            # let ssh-keygen do its job
            subprocess.check_output(['ssh-keygen',
                '-f', self.path,
                '-t', self.key_algorithm,
                '-C', self.name])

            # write the serial file with a value of
            # 0 for first certificate
            with open(self.path + '.serial', 'w') as stream:
                stream.write(str(0))

            super(SSHAuthority, self).generate()


        else:
            raise ValueError('A CA with the same id and type already exists')


    def sign(self, request):

        assert type(request) in self.request_allowed

        pub_key_path = request.destination
        cert_path = Certificate(request.req_id).path

        with open(self.path + '.serial', 'r') as stream:
            next_serial = int(stream.read())
        with open(self.path + '.serial', 'w') as stream:
            stream.write(str(next_serial + 1))

        with open(request.destination, 'w') as stream:
            stream.write(request.key_data)

        ca_private_key = self.path

        if type(request) == UserSSHRequest:
            login_names = [ request.user_name, ]
            if request.root_requested:
                login_names.append('root')

            subprocess.check_output(['ssh-keygen',
                '-s', ca_private_key,
                '-I', 'user_%s' % request.user_name,
                '-n', ','.join(login_names),
                '-V', self.user_validity,
                '-z', str(next_serial),
                pub_key_path])
        elif type(request) == HostSSHRequest:
            subprocess.check_output(['ssh-keygen',
                '-s', ca_private_key,
                '-I', 'host_%s' % request.host_name.replace('.', '_'),
                '-h',
                '-n', request.host_name,
                '-V', self.host_validity,
                '-z', str(next_serial),
                pub_key_path])

        return cert_path

class SSLAuthority(Authority):
    request_allowed = [ HostSSLRequest, ]

    ca_key_algorithm = 'des3'
    key_length = '4096'

    key_algorithm = 'sha256'
    ca_validity = '365'
    cert_validity = '365'

    def __init__(self, ca_id):
        ssl_ca_dir = os.path.join(MANAGER_PATH, 'ssl_ca')

        super(SSLAuthority, self).__init__(ca_id, ssl_ca_dir)

    def generate(self):
        if os.path.exists(self.path):
            raise ValueError("A CA with the same id and type already exists")

        subprocess.check_output(['openssl',
            'genrsa',
            '-%s'%self.ca_key_algorithm,
            '-out', '%s'%(self.path),
            self.key_length])

        subprocess.check_output(['openssl',
            'req',
            '-new',
            '-x509',
            '-days', self.ca_validity,
            '-key', self.path,
            # '-extensions', 'v3_ca'
            '-out', "%s.pub"%self.path,
            # '-config', "%s.conf"%self.path
            ])

        with open(self.path + '.serial', 'w') as stream:
            stream.write(str(0))


    def sign(self, request):
        OUTPUT_PATH

        assert type(request) in self.request_allowed

        pub_key_path = os.path.join(OUTPUT_PATH, request.req_id + '.pub')
        cert_path = os.path.join(OUTPUT_PATH, request.req_id + '-cert.pub')

        with open(self.path + '.serial', 'r') as stream:
            next_serial = int(stream.read())
        with open(self.path + '.serial', 'w') as stream:
            stream.write(str(next_serial + 1))

        with open(pub_key_path, 'w') as stream:
            stream.write(request.key_data)

        ca_private_key = self.path

        # openssl x509 -req -days 360 -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial -out server.crt        # print()
        subprocess.check_output(['openssl',
                        'x509',
                        '-req',
                        '-days', self.ca_validity,
                        '-in', pub_key_path,
                        '-CA', "%s.pub"%self.path,
                        '-CAkey', self.path,
                        '-CAcreateserial',
                        '-out', cert_path,
                        '-%s'%self.key_algorithm])

        return cert_path
