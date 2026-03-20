---
- 0. Table of Contents
	---
- 1. Problem Statements
	- Problem & Context
		OVN over TCP poses security risks to Openstack Network so SSL deployment is required.
	- Desired Outcome
		1. SSL for OVN NB DB and its Clients
		1. SSL for OVN SB DB and its Clients
		1. SSL for OVSDB Server and its Clients
---
- 2. Research Result
	- 0. Init
		- 1. Current Status
			![](https://net-docs.infiniband.vn/api/file_storage/e65d18a1-501f-4a93-a67f-a1c5c8c7336d/v1/blob/b509ece0%2Dfd9a%2D4b9e%2Da4ef%2D9df3adbfe975/bfEfpUpgKaR4WA8_Z8Df7acRjTOdDmC4GwH9gzyYwmg=.png)
		- 2. SSL Certificates Preparation
			#### 1. Create Root CA ECDSA-256
			**Prepare SSL certificates** by creating a **Root Certificate Authority (Root CA)** using **ECDSA with the P-256 curve**.
			A Root CA is the **trust anchor** of a PKI (Public Key Infrastructure).
			All other certificates (server, client, component certificates) will eventually be **signed by this CA**, so its configuration must be precise and conservative.
			```
			# 1. Create an OpenSSL configuration file (req-ca.conf)
			cat > req-ca.cnf << 'EOF'
			[ req ]
			default_bits        = 256
			distinguished_name  = req_distinguished_name
			req_extensions      = v3_req
			default_md          = sha256
			prompt              = no

			[ req_distinguished_name ]
			C  = US
			ST = CA
			OU = OVN CA
			CN = OVN CA Certificate

			[ v3_req ]
			basicConstraints = CA:FALSE
			keyUsage         = digitalSignature, keyEncipherment
			extendedKeyUsage = serverAuth, clientAuth

			EOF

			# 2. Generate the ECDSA private key
			openssl ecparam -name prime256v1 -genkey -out cakey.pem

			# 3. Create a self-signed Root CA certificate
			openssl req -x509 -new -nodes \
			  -key cakey.pem \
			  -sha256 -days 36500 \
			  -out cacert.pem \
			  -config req-ca.conf
			```
			#### 2. Upload CA Cert and CA Key on Vault
			![](https://net-docs.infiniband.vn/api/file_storage/e65d18a1-501f-4a93-a67f-a1c5c8c7336d/v1/blob/b509ece0%2Dfd9a%2D4b9e%2Da4ef%2D9df3adbfe975/FXhQI1tHmZbtH8zbyxTfC6lHsXdKB9K_aZSWtcCnt94=.png)
			#### 3. Generate & Distribute TLS Certificates using Ansible
			##### High-level Goal (Big Picture)
			This step automates **certificate lifecycle management** for three OVN-related roles:
			1. **Controller node**
			1. **Compute / Network node (ovn-controller)**
			1. **SDN Agent**
			It does so by:
			* Pulling the **Root CA** from **Vault**
			* Generating **private keys and CSRs locally**
			* Signing certificates with the CA
			* Distributing certificates only to the nodes that need them
			* Cleaning up sensitive artifacts on the deploy node
			* Persisting SDN-agent credentials back into Vault
			This is a **centralized CA + decentralized key generation** model, which is a good security practice.
			##### Phase 0: Detect Existing Certificates
			*   On **compute / network nodes**:
				*   Does `ovn-controller-cert.pem` already exist?
			*   On **controller nodes**:
				*   Does `ovn-cert.pem` already exist?
				```
				- name: Check OVN cert on compute/network nodes
				  stat:
				    path: "{{ internal_dir }}/ovn-controller-cert.pem"
				    register: ovn_compute_cert
				    when: "'compute' in group_names or 'network' in group_names"

				- name: Check OVN cert on controller node
				  stat:
				    path: "{{ internal_dir }}/ovn-cert.pem"
				    register: ovn_controller_cert
				    when: "'control' in group_names"
				```##### Phase 1: Load Root CA from Vault (Trust Anchor)
			Ansible retrieves:
			* `cacert.pem` (Root CA certificate)
			* `cakey.pem` (Root CA private key)
			```
			- name: Load CA secrets from Vault
			  set_fact:
			    ovn_ca:
			      cert: "{{ secret_data[site_name ~ '-cacert']}}"
			      key: "{{ secret_data[site_name ~ '-cakey']}}"
			  vars:
			    secret_data" >-
			      {{ lookup(
			        'community.hashi_vault.hashi_vault',
			        'cloud/profile/data/app/openstack/ovn-ssl' ~ site_name,
			        url=vault_addr,
			        token=vault_token
			        ) }}
			  delegate_to: localhost
			  
			- name: Check if SDN-AGENT secret exists
			  set_fact:
			    sdn_secret: >-
			      {{ lookup(
			        'community.hashi_vault.hashi_vault',
			        'cloud/profile/data/app/openstack/sdn-agent/{{ site_name }}',
			        url=vault_addr,
			        token=vault_token
			        ) }}
			  delegate_to: localhost
			```
			##### Phase 2: Prepare Secure Working Directories
			```
			- name: Ensure ovn-ssl working directory exists
			  file:
			    path: "{{ internal_dir }}"
			    state: directory
			    mode: "0755"

			- name: Ensure private directories exist on deploy node
			  file:
			    path: "{{ internal_dir }}/{{ item }}"
			    state: directory
			    mode: "0700"
			  loop:
			    - root
			    - controller
			    - compute
			    - sdn-agent
			  delegate_to: localhost
			```
			##### Phase 3: Controller Node Certificate
			```
			- block:
			    - name: Render controller OpenSSL config
			      template:
			        src: req-control.conf.j2
			        dest: "{{ internal_dir }}/controller/req-control.conf"
			        mode: "0660"
			      delegate_to: localhost

			    - name: Generate controller private key
			      command: >
			        openssl ecparam -name prime256v1 -genkey
			        -out {{ internal_dir }}/controller/ovn-privkey.pem
			      args:
			        creates: "{{ internal_dir }}/controller/ovn-privkey.pem"
			      delegate_to: localhost

			    - name: Generate controller CSR
			      command: >
			        openssl req -new -sha256
			        -key {{ internal_dir }}/controller/ovn-privkey.pem
			        -out {{ internal_dir }}/controller/ovn.csr
			        -config {{ internal_dir }}/controller/req-control.conf
			      args:
			        creates: "{{ internal_dir }}/controller/ovn.csr"
			      delegate_to: localhost

			    - name: Write CA cert and key locally
			      copy:
			        content: "{{ item.content }}"
			        dest: "{{ internal_dir }}/root/{{ item.dest }}"
			        mode: "0600"
			      loop:
			        - { content: "{{ ovn_ca.cert }}", dest: cacert.pem }
			        - { content: "{{ ovn_ca.key }}",  dest: cakey.pem  }
			      delegate_to: localhost

			    - name: Sign controller certificate
			      command: >
			        openssl x509 -req
			        -in {{ internal_dir }}/controller/ovn.csr
			        -CA {{ internal_dir }}/root/cacert.pem
			        -CAkey {{ internal_dir }}/root/cakey.pem
			        -CAcreateserial
			        -out {{ internal_dir }}/controller/ovn-cert.pem
			        -days 36500
			        -sha256
			        -extensions v3_req
			        -extfile {{ internal_dir }}/controller/req-control.conf
			      args:
			        creates: "{{ internal_dir }}/controller/ovn-cert.pem"
			      delegate_to: localhost
			  when: not (ovn_controller_cert.stat.exists | default(true))
			```
			##### Phase 5: Deploy Controller Certificates
			```
			- name: Copy controller cert and key
			  copy:
			    src: "{{ internal_dir }}/controller/{{ item }}.pem"
			    dest: "{{ internal_dir }}/{{ item }}.pem"
			    mode: "0644"
			  loop:
			    - ovn-cert
			    - ovn-privkey
			  when: "'control' in group_names"

			- name: Copy CA cert to controller
			  copy:
			    src: "{{ internal_dir }}/root/cacert.pem"
			    dest: "{{ internal_dir }}/cacert.pem"
			    mode: "0644"
			  when: "'control' in group_names"
			```
			##### Phase 6: Compute / Network (ovn-controller) Certificates
			Same pattern as controller, but:
			* Uses `req-ovn-controller.conf`
			* Outputs:
				* `ovn-controller-cert.pem`
				* `ovn-controller-privkey.pem`
			* Deployed only to `compute` and `network` groups
			**Kolla convention: **One certificate per service role
			##### Phase 7: SDN Agent Certificate Workflow
			```
			- block:
			    - name: Render SDN Agent OpenSSL config
			      template:
			        src: req-sdn-agent.conf.j2
			        dest: "{{ internal_dir }}/sdn-agent/req-sdn-agent.conf"
			        mode: "0660"
			      delegate_to: localhost

			    - name: Generate SDN Agent private key
			      command: >
			        openssl ecparam -name prime256v1 -genkey
			        -out {{ internal_dir }}/sdn-agent/ovn-sdn-agent-privkey.pem
			      args:
			        creates: "{{ internal_dir }}/sdn-agent/ovn-sdn-agent-privkey.pem"
			      delegate_to: localhost

			    - name: Generate SDN Agent CSR
			      command: >
			        openssl req -new -sha256
			        -key {{ internal_dir }}/sdn-agent/ovn-sdn-agent-privkey.pem
			        -out {{ internal_dir }}/sdn-agent/ovn.csr
			        -config {{ internal_dir }}/sdn-agent/req-sdn-agent.conf
			      args:
			        creates: "{{ internal_dir }}/sdn-agent/ovn.csr"
			      delegate_to: localhost

			    - name: Sign SDN Agent certificate
			      command: >
			        openssl x509 -req
			        -in {{ internal_dir }}/sdn-agent/ovn.csr
			        -CA {{ internal_dir }}/root/cacert.pem
			        -CAkey {{ internal_dir }}/root/cakey.pem
			        -CAcreateserial
			        -out {{ internal_dir }}/sdn-agent/ovn-sdn-agent-cert.pem
			        -days 36500
			        -sha256
			        -extensions v3_req
			        -extfile {{ internal_dir }}/sdn-agent/req-sdn-agent.conf
			      args:
			        creates: "{{ internal_dir }}/sdn-agent/ovn-sdn-agent-cert.pem"
			      delegate_to: localhost
			     
			```
			##### Phase 8: Persist SDN Agent Credentials into Vault
			```
			- name: Upload SDN Agent certs to Vault
			  community.hashi_vault.vault_write:
			    url: "{{ vault_addr }}"
			    token: "{{ vault_token }}"
			    path: "cloud/profile/data/app/openstack/sdn-agent/{{ site_name }}"
			    data:
			      cacert:      "{{ cacert_pem.content | b64decode }}"
			      sdn_cert:    "{{ agent_cert.content | b64decode }}"
			      sdn_privkey: "{{ agent_privkey.content | b64decode }}"
			```
			##### Phase 9: Cleanup on Deploy Node
			```
			- name: Remove certificate workspace on deploy node
			  file:
			    path: "{{ internal_dir }}"
			    state: absent
			  delegate_to: localhost
			```
			![](https://net-docs.infiniband.vn/api/file_storage/e65d18a1-501f-4a93-a67f-a1c5c8c7336d/v1/blob/b509ece0%2Dfd9a%2D4b9e%2Da4ef%2D9df3adbfe975/94myRDsoirK7SZLJOzwoOXzAvs-h7W2RpwCKmuKY9V8=.png)
	- 1. SSL for OVN Northbound Database and its Clients
		Adding Config to kolla global .yml
		```
		# Extra volume mount ovn-ssl into containers
		neutron_extra_volumes:
		  - "/etc/kolla/ovn-ssl:/etc/neutron/ovn-ssl"
		octavia_extra_volumes:
		  - "/etc/kolla/ovn-ssl:/etc/octavia/ovn-ssl"
		ovn_sb_db_extra_volumes:
		  - "/etc/kolla/ovn-ssl:/etc/ovn/ovn-ssl"
		ovn_controller_extra_volumes:
		  - "/etc/kolla/ovn-ssl:/etc/ovn/ovn-ssl"
		neutron_ovn_metadata_agent_extra_volumes:
		  - "/etc/kolla/ovn-ssl:/etc/neutron/ovn-ssl"
		ovn_nb_db_extra_volumes:
		  - "/etc/kolla/ovn-ssl:/etc/ovn/ovn-ssl"
		ovn_northd_extra_volumes:
		  - "/etc/kolla/ovn-ssl:/etc/ovn/ovn-ssl"
		```
		- 1. Enable SSL for ovn-nb-db (Client - Server Connection)
			```
			root@hni-cloud-hci-controller-101:/home/dattt4# docker exec ovn_nb_db ovn-nbctl --no-leader-only list connection
			_uuid               : ce4a5ae3-e149-4fc6-928a-6256713b3633
			external_ids        : {}
			inactivity_probe    : []
			is_connected        : true
			max_backoff         : []
			other_config        : {}
			status              : {}
			target              : "pssl:6647:0.0.0.0"

			root@hni-cloud-hci-controller-101:/home/dattt4# docker exec ovn_nb_db ovn-nbctl --no-leader-only list ssl
			_uuid               : e353b5b2-aff0-4fb1-924f-4612a5a06df0
			bootstrap_ca_cert   : false
			ca_cert             : "/etc/ovn/ovn-ssl/cacert.pem"
			certificate         : "/etc/ovn/ovn-ssl/ovn-cert.pem"
			external_ids        : {}
			private_key         : "/etc/ovn/ovn-ssl/ovn-privkey.pem"
			ssl_ciphers         : ""
			ssl_protocols       : ""
			```
			```
			# kolla global.yml
			ovn_nb_db_port: "6647"
			ovn_nb_db_connection: {% for host in groups['ovn-nb-db'] %}ssl:{{ 'api' | kolla_address(host) | put_address_in_context('url') }}:{{ ovn_nb_db_port }}{% if not loop.last %},{% endif %}{% endfor %}
			--private-key=/etc/ovn/ovn-ssl/ovn-privkey.pem
			--cerificate=/etc/ovn/ovn-ssl/ovn-cert.pem
			--ca-cert=/etc/ovn/ovn-ssl/cacert.pem

			ovn_sb_db_port: "6649"
			ovn_sb_db_connection: {% for host in groups['ovn-sb-db'] %}ssl:{{ 'api' | kolla_address(host) | put_address_in_context('url') }}:{{ ovn_sb_db_port }}{% if not loop.last %},{% endif %}{% endfor %}

			ovn_sb_db_port_control: "6648"
			ovn_sb_db_connection: {% for host in groups['ovn-sb-db'] %}ssl:{{ 'api' | kolla_address(host) | put_address_in_context('url') }}:{{ ovn_sb_db_port_control }}{% if not loop.last %},{% endif %}{% endfor %}
			```- 2. Enable SSL for neutron-server → ovn-nb-db
			```
			# /etc/kolla/config/neutron/ml2_conf.ini
			ovn_nb_connection = ssl:10.102.19.101:6647,ssl:10.102.19.102:6647,ssl:10.102.19.103:6647
			ovn_nb_private_key = /etc/neutron/ovn-ssl/ovn-privkey.pem
			ovn_nb_certificate = /etc/neutron/ovn-ssl/ovn-cert.pem
			ovn_nb_ca_cert = /etc/neutron/ovn-ssl/cacert.pem
			```- 3. Enable SSL for apache2 → ovn-nb-db
			```
			# Same config with octavia-driver because this is the octavia-api 
			```- 4. Enable SSL for octavia-driver → ovn-nb-db
			```
			# /etc/kolla/config/octavia.conf

			[ovn]
			ovn_nb_connection = ssl:10.102.19.101:6647,ssl:10.102.19.102:6647,ssl:10.102.19.103:6647
			ovn_nb_private_key = /etc/octavia/ovn-ssl/ovn-privkey.pem
			ovn_nb_certificate = /etc/octavia/ovn-ssl/ovn-cert.pem
			ovn_nb_ca_cert = /etc/octavia/ovn-ssl/cacert.pem
			```- 5. Enable SSL for ovn-northd → ovn-nb-db
			```
			# ansible/roles/ovn-db/templates/ovn-northd.json.j2

			{
			    "command": "/usr/bin/ovn-northd -vconsole:emer -vsyslog:err -vfile:info --ovnnb-db={{ ovn_nb_connection }} --ovnsb-db={{ ovn_sb_connection_control }} --log-file=/var/log/kolla/openvswitch/ovn-northd.log --pidfile=/run/ovn/ovn-northd.pid --unixctl=/run/ovn/ovn-northd.ctl",
			    "permissions": [
			        {
			            "path": "/var/log/kolla/openvswitch",
			            "owner": "root:root",
			            "recurse": true
			        }
			    ]
			}
			```- 6. Disable TCP for ovn-nb-db (Client - Server connection)
			```
			docker exec ovn_nb_db ovn-nbctl --no-leader-only remove NB_Global . connections <uuid>
			```- 7. Enable SSL for ovn-nb-db Clustering
			```
			# Edit ansible/roles/ovn-db/defaults/main.yml

			ovn_nb_command: >-
			  /usr/share/ovn/scripts/ovn-ctl run_nb_ovsdb
			  --db-nb-ca-cert=/path/to/ca.crt
			  --db-nb-cert=/path/to/server.crt
			  --db-nb-privkey=/path/to/server.key
			  ...
			  
			# Need further investigation
			```

	- 2. SSL for OVN Southbound Database and its Clients
		- 1. Enable SSL for ovn-sb-db (Client - Server Connection)
			```
			root@hni-cloud-hci-controller-101:/home/dattt4# docker exec ovn_sb_db ovn-sbctl --no-leader-only list connection
			_uuid               : 54fd16bd-4680-4d33-a80d-61653bdf06fc
			external_ids        : {}
			inactivity_probe    : []
			is_connected        : true
			max_backoff         : []
			other_config        : {}
			read_only           : false
			role                : ""
			status              : {}
			target              : "pssl:6648:0.0.0.0"

			_uuid               : 19ac9c7b-d661-4b91-b76b-afef7d48b70a
			external_ids        : {}
			inactivity_probe    : []
			is_connected        : true
			max_backoff         : []
			other_config        : {}
			read_only           : false
			role                : ovn-controller
			status              : {}
			target              : "pssl:6649:0.0.0.0"

			root@hni-cloud-hci-controller-101:/home/dattt4# docker exec ovn_sb_db ovn-sbctl --no-leader-only list ssl
			_uuid               : 04850643-b10c-4e9a-9ea1-85aad0ca80e0
			bootstrap_ca_cert   : false
			ca_cert             : "/etc/ovn/ovn-ssl/cacert.pem"
			certificate         : "/etc/ovn/ovn-ssl/ovn-cert.pem"
			external_ids        : {}
			private_key         : "/etc/ovn/ovn-ssl/ovn-privkey.pem"
			ssl_ciphers         : ""
			ssl_protocols       : ""
			```- 2. Enable SSL for ovn-controller → ovn-sb-db
			```
			# ansible/roles/ovn-controller/tasks/setup-ovs.yml
			---
			- name: Create br-int bridge on OpenvSwitch
			  become: true
			  kolla_toolbox:
			    container_engine: "{{ kolla_container_engine }}"
			    user: root
			    module_name: openvswitch_bridge
			    module_args:
			      bridge: br-int
			      state: present
			      fail_mode: secure

			- name: Configure OVN in OVSDB
			  vars:
			    # Format: physnet1:br1,physnet2:br2
			    ovn_mappings: "{{ neutron_physical_networks.split(',') | zip(neutron_bridge_name.split(',')) | map('join', ':') | join(',') }}"
			    # Format: physnet1:00:11:22:33:44:55,physnet2:00:11:22:33:44:56
			    ovn_macs: "{% for physnet, bridge in neutron_physical_networks.split(',') | zip(neutron_bridge_name.split(',')) %}{{ physnet }}:{{ ovn_base_mac | random_mac(seed=inventory_hostname + bridge) }}{% if not loop.last %},{% endif %}{% endfor %}"
			    ovn_cms_opts: "{{ 'enable-chassis-as-gw' if inventory_hostname in groups['ovn-controller-network'] else '' }}{{ ',availability-zones=' + neutron_ovn_availability_zones | join(',') if inventory_hostname in groups['ovn-controller-network'] and neutron_ovn_availability_zones }}"
			  become: true
			  kolla_toolbox:
			    container_engine: "{{ kolla_container_engine }}"
			    user: root
			    module_name: openvswitch_db
			    module_args:
			      table: Open_vSwitch
			      record: .
			      col: external_ids
			      key: "{{ item.name }}"
			      value: "{{ item.value if item.state | default('present') == 'present' else omit }}"
			      state: "{{ item.state | default('present') }}"
			  loop:
			    - { name: ovn-encap-ip, value: "{{ tunnel_interface_address }}" }
			    - { name: ovn-encap-type, value: geneve }
			    - { name: ovn-remote, value: "{{ ovn_sb_connection }}" }
			    - { name: ovn-remote-probe-interval, value: "{{ ovn_remote_probe_interval }}" }
			    - { name: ovn-openflow-probe-interval, value: "{{ ovn_openflow_probe_interval }}" }
			    - { name: ovn-monitor-all, value: "{{ ovn_monitor_all | bool }}" }
			    - { name: ovn-bridge-mappings, value: "{{ ovn_mappings }}", state: "{{ 'present' if (inventory_hostname in groups['ovn-controller-network'] or computes_need_external_bridge | bool) else 'absent' }}" }
			    - { name: ovn-chassis-mac-mappings, value: "{{ ovn_macs }}", state: "{{ 'present' if inventory_hostname in groups['ovn-controller-compute'] else 'absent' }}" }
			    - { name: ovn-cms-options, value: "{{ ovn_cms_opts }}", state: "{{ 'present' if ovn_cms_opts != '' else 'absent' }}" }
			  when: inventory_hostname in groups.get('ovn-controller', [])

			```- 3. Enable SSL for neutron-server → ovn-sb-db
			```
			# /etc/kolla/config/neutron/ml2_conf.ini

			ovn_sb_connection = ssl:10.102.19.101:6648,ssl:10.102.19.102:6648,ssl:10.102.19.103:6648
			ovn_sb_private_key = /etc/neutron/ovn-ssl/ovn-privkey.pem
			ovn_sb_certificate = /etc/neutron/ovn-ssl/ovn-cert.pem
			ovn_sb_ca_cert = /etc/neutron/ovn-ssl/cacert.pem
			```- 4. Enable SSL for octavia-driver → ovn-sb-db
			```
			# /etc/kolla/config/octavia.conf

			[ovn]
			ovn_sb_connection = ssl:10.102.19.101:6648,ssl:10.102.19.102:6648,ssl:10.102.19.103:6648
			ovn_sb_private_key = /etc/octavia/ovn-ssl/ovn-privkey.pem
			ovn_sb_certificate = /etc/octavia/ovn-ssl/ovn-cert.pem
			ovn_sb_ca_cert = /etc/octavia/ovn-ssl/cacert.pem
			```

		- 5. Enable SSL for ovn-northd → ovn-sb-db
			```
			# ansible/roles/ovn-db/templates/ovn-northd.json.j2

			{
			    "command": "/usr/bin/ovn-northd -vconsole:emer -vsyslog:err -vfile:info --ovnnb-db={{ ovn_nb_connection }} --ovnsb-db={{ ovn_sb_connection_control }} --log-file=/var/log/kolla/openvswitch/ovn-northd.log --pidfile=/run/ovn/ovn-northd.pid --unixctl=/run/ovn/ovn-northd.ctl",
			    "permissions": [
			        {
			            "path": "/var/log/kolla/openvswitch",
			            "owner": "root:root",
			            "recurse": true
			        }
			    ]
			}
			```- 6. Enable SSL for neutron-ovn-metadata_agent → ovn-sb-db
			```
			# /etc/kolla/config/neutron/neutron_ovn_metadata_agent.ini

			[ovn]
			ovn_nb_connection = ssl:10.102.19.101:6647,ssl:10.102.19.102:6647,ssl:10.102.19.103:6647 # ?
			ovn_sb_connection = ssl:10.102.19.101:6649,ssl:10.102.19.102:6649,ssl:10.102.19.103:6649
			ovn_metadata_enabled = true
			ovn_sb_private_key = /etc/neutron/ovn-ssl/ovn-controller-privkey.pem
			ovn_sb_certificate = /etc/neutron/ovn-ssl/ovn-controller-cert.pem
			ovn_sb_ca_cert = /etc/neutron/ovn-ssl/cacert.pem
			```- 7. Disable TCP for ovn-sb-db (Client - Server Connection)
			```
			docker exec ovn_sb_db ovn-nbctl --no-leader-only remove SB_Global . connections <uuid>
			```- 8. Enable SSL for ovn-sb-db Clustering
			```
			# Edit ansible/roles/ovn-db/defaults/main.yml

			ovn_sb_command: >-
			  /usr/share/ovn/scripts/ovn-ctl run_sb_ovsdb
			  --db-sb-ca-cert=/path/to/ca.crt
			  --db-sb-cert=/path/to/server.crt
			  --db-sb-privkey=/path/to/server.key
			  ...
			  
			# Need further investigation
			```

	- 3. SSL for OVS DB Server and its Clients
		- 1. Enable SSL for ovsdb-server
			```
			ovs-vsctl set-manager pssl:6640:127.0.0.1   -- set Manager . inactivity_probe=30000 max_backoff=90000

			root@hni-cloud-hci-controller-101:/home/dattt4# docker exec openvswitch_db ovs-vsctl list open_vswitch
			_uuid               : a15928f9-8567-48dd-9f06-c378a8a99b09
			bridges             : [40d76b2c-d171-4ef8-a264-e140a1c47e11, 89889ce3-acdd-4b2e-881e-96037deb7c3b]
			cur_cfg             : 1823
			datapath_types      : [netdev, system]
			datapaths           : {system=30d673fb-8ee1-4faf-91f7-886c3fa16461}
			db_version          : []
			dpdk_initialized    : false
			dpdk_version        : none
			external_ids        : {hostname=hni-cloud-hci-controller-101.vnpaycloud.vn, ovn-bridge-mappings="vlan:br-ex", ovn-chassis-mac-mappings="vlan:52:54:00:ed:3b:68", ovn-cms-options=enable-chassis-as-gw, ovn-encap-ip="10.102.19.101", ovn-encap-type=geneve, ovn-monitor-all="false", ovn-openflow-probe-interval="60", ovn-remote="ssl:10.102.19.101:6649,ssl:10.102.19.102:6649,ssl:10.102.19.103:6649", ovn-remote-probe-interval="60000", system-id=hni-cloud-hci-controller-101}
			iface_types         : [afxdp, afxdp-nonpmd, bareudp, erspan, geneve, gre, gtpu, internal, ip6erspan, ip6gre, lisp, patch, srv6, stt, system, tap, vxlan]
			manager_options     : [e7155ff1-2cc8-4f06-865a-a77f1759a0a8]
			next_cfg            : 1823
			other_config        : {ovn-chassis-idx-hni-cloud-hci-controller-101="", vlan-limit="0"}
			ovs_version         : []
			ssl                 : 58b5d708-2cab-4a6f-9b0e-cc70444f33c2
			statistics          : {}
			system_type         : []
			system_version      : []


			root@hni-cloud-hci-controller-101:/home/dattt4# docker exec openvswitch_db ovs-vsctl list ssl
			_uuid               : 58b5d708-2cab-4a6f-9b0e-cc70444f33c2
			bootstrap_ca_cert   : false
			ca_cert             : "/etc/ovn/ovn-ssl/cacert.pem"
			certificate         : "/etc/ovn/ovn-ssl/ovn-controller-cert.pem"
			external_ids        : {}
			private_key         : "/etc/ovn/ovn-ssl/ovn-controller-privkey.pem"
			```- 2. Enable SSL for ovn-controller → ovsdb-server
			```
			{
			    "command": "/usr/bin/ovn-controller --pidfile=/run/ovn/ovn-controller.pid --log-file=/var/log/kolla/openvswitch/ovn-controller.log ssl:127.0.0.1:{{ ovsdb_port }}",
			    "permissions": [
			        {
			            "path": "/var/log/kolla/openvswitch",
			            "owner": "root:root",
			            "recurse": true
			        }
			    ]
			}
			```- 3. Enable SSL for nova-compute → ovsdb-server
			Currently not supported by Kolla-Ansible (Need to verify Nova & Neutron)
		- 4. Enable SSL for neutron-ovn-met → ovsdb-server
			Currently not supported by Kolla-Ansible (Need to verify Nova & Neutron)
		- 5. Disable TCP for ovsdb-server

	- 4. Action Plan
		### 1. Create CA Cert
		### 2. Add iptables for OVN SSL
		```
		ansible-playbook -i /root/hni-ops04-sdn-sb-2024-02/multinode setup-iptables-pci.yml -k -b -K
		```
		### 3. Setup OVN-SSL
		```
		ansible-playbook -i /root/hni-ops04-sdn-sb-2024-02/multinode setup-ovn.yml -k -b -k
		```
		### 4. Reconfigure OVN Limit Controller
		```
		kolla-ansible deploy -i multinode --tags ovn --limit control
		```
		### 5. Reconfigure Octavia
		```
		kolla-ansible deploy -i multinode --tags octavia --limit control
		```
		### 6. Reconfigure Neutron
		```
		kolla-ansible deploy -i multinode --tags otavia???
		```
		### 7. Reconfigure OVN on Network & Compute Nodes
		```
		kolla-ansible deploy -i multinode --tags ovn -limit compute
		```
		### 8. Check Logs and Services

		### 9. Remove OVN TCP Config

- 

