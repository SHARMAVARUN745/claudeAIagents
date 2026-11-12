# DataNode volume failure
Symptoms: DATA_NODE_VOLUME_FAILURES BAD, under-replicated blocks rising.
Read-only checks: CM > hdfs > DataNode > Charts; `hdfs dfsadmin -report`; `dmesg | grep -i 'I/O error'` on the host.
Fix (REQUIRES CHANGE APPROVAL): replace disk, then decommission/recommission volume per vendor SOP.

# NameNode long GC pause
Check NN heap in CM, `jstat -gcutil <pid> 1000 5`. Remediation: raise heap or reduce small files (REQUIRES CHANGE APPROVAL).
