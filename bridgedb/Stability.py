# -*- coding: utf-8 ; test-case-name: bridgedb.test.test_Stability -*-
#
# This file is part of BridgeDB, a Tor bridge distribution system.
#
# :authors: please see the AUTHORS file for attributions
# :copyright: (c) 2013-2017, Isis Lovecruft
#             (c) 2013-2017, Matthew Finkel
#             (c) 2012-2017, Aaron Gibson
#             (c) 2007-2017, Nick Mathewson
#             (c) 2007-2017, The Tor Project, Inc.
# :license: see LICENSE for licensing information

"""This module provides functionality for tracking bridge stability metrics.

Bridge stability metrics are calculated using the model introduced in
`"An Analysis of Tor Bridge Stability"`_ and
`implemented in the Tor Metrics library`_.

.. An Analysis of Tor Bridge Stability:
    https://metrics.torproject.org/papers/bridge-stability-2011-10-31.pdf
    Karsten Loesing, An Analysis of Tor Bridge Stability. Technical Report.
    The Tor Project, October 2011.

.. implemented in the Tor Metrics library:
    https://gitweb.torproject.org/metrics-tasks/task-4255/SimulateBridgeStability.java
"""

import logging
import bridgedb.Storage

from bridgedb.schedule import toUnixSeconds


# tunables 
weighting_factor = float(19)/float(20)
discountIntervalMillis = 60*60*12*1000


class BridgeHistory(object):
    """ Record Class that tracks a single Bridge
    The fields stored are:

    fingerprint, ip, port, weightedUptime, weightedTime, weightedRunLength,
    totalRunWeights, lastSeenWithDifferentAddressAndPort,
    lastSeenWithThisAddressAndPort, lastDiscountedHistoryValues.

    fingerprint         The Bridge Fingerprint (unicode)
    ip                  The Bridge IP (unicode)
    port                The Bridge orport (integer)

    weightedUptime      Weighted uptime in seconds (long int)
    weightedTime        Weighted time in seconds (long int)
    weightedRunLength   Weighted run length of previous addresses or ports in
                        seconds. (long int)
    totalRunWeights     Total run weights of previously used addresses or
                        ports. (float)

    lastSeenWithDifferentAddressAndPort
        Timestamp in milliseconds when this
        bridge was last seen with a different address or port. (long int)

    lastSeenWithThisAddressAndPort
        Timestamp in milliseconds when this bridge was last seen
        with this address and port. (long int)

    lastDiscountedHistoryValues:
        Timestamp in milliseconds when this bridge was last discounted. (long int)

    lastUpdatedWeightedTime:
        Timestamp in milliseconds when the weighted time was updated. (long int)
    """
    def __init__(self, fingerprint, ip, port,
            weightedUptime, weightedTime, weightedRunLength, totalRunWeights,
            lastSeenWithDifferentAddressAndPort, lastSeenWithThisAddressAndPort,
            lastDiscountedHistoryValues, lastUpdatedWeightedTime):
        self.fingerprint = fingerprint
        self.ip = ip 
        self.port = port
        self.weightedUptime = int(weightedUptime)
        self.weightedTime = int(weightedTime)
        self.weightedRunLength = int(weightedRunLength)
        self.totalRunWeights = float(totalRunWeights)
        self.lastSeenWithDifferentAddressAndPort = \
                int(lastSeenWithDifferentAddressAndPort)
        self.lastSeenWithThisAddressAndPort = int(lastSeenWithThisAddressAndPort)
        self.lastDiscountedHistoryValues = int(lastDiscountedHistoryValues)
        self.lastUpdatedWeightedTime = int(lastUpdatedWeightedTime)

    def discountWeightedFractionalUptimeAndWeightedTime(self, discountUntilMillis):
        """ discount weighted times """
        if self.lastDiscountedHistoryValues == 0:
            self.lastDiscountedHistoryValues = discountUntilMillis
        rounds = self.numDiscountRounds(discountUntilMillis)
        if rounds > 0:
            discount = lambda x: (weighting_factor**rounds)*x
            self.weightedUptime = discount(self.weightedUptime)
            self.weightedTime = discount(self.weightedTime)
            self.weightedRunLength = discount(self.weightedRunLength)
            self.totalRunWeights = discount(self.totalRunWeights)

            self.lastDiscountedHistoryValues += discountIntervalMillis * rounds
        return rounds

    def numDiscountRounds(self, discountUntilMillis):
        """ return the number of rounds of discounting needed to bring this
        history element current """
        result = discountUntilMillis - self.lastDiscountedHistoryValues
        result = int(result/discountIntervalMillis)
        return max(result,0)

    @property
    def weightedFractionalUptime(self):
        """Weighted Fractional Uptime"""
        if self.weightedTime <0.0001: return 0
        return 10000 * self.weightedUptime / self.weightedTime

    @property
    def tosa(self):
        """the Time On Same Address (TOSA)"""
        return ( self.lastSeenWithThisAddressAndPort - \
                    self.lastSeenWithDifferentAddressAndPort ) / 1000

    @property
    def familiar(self):
        """
        A bridge is 'familiar' if 1/8 of all active bridges have appeared
        more recently than it, or if it has been around for a Weighted Time of 8 days.
        """
        # if this bridge has been around longer than 8 days
        if self.weightedTime >= 8 * 24 * 60 * 60:
            return True

        # return True if self.weightedTime is greater than the weightedTime
        # of the > bottom 1/8 all bridges, sorted by weightedTime
        with bridgedb.Storage.getDB() as db:
            allWeightedTimes = [ bh.weightedTime for bh in db.getAllBridgeHistory()]
            numBridges = len(allWeightedTimes)
            logging.debug("Got %d weightedTimes", numBridges)
            allWeightedTimes.sort()
            if self.weightedTime >= allWeightedTimes[numBridges/8]:
                return True
            return False

    @property
    def wmtbac(self):
        """Weighted Mean Time Between Address Change"""
        totalRunLength = self.weightedRunLength + \
                ((self.lastSeenWithThisAddressAndPort -
                self.lastSeenWithDifferentAddressAndPort) / 1000)

        totalWeights = self.totalRunWeights + 1.0
        if totalWeights <  0.0001: return 0
        assert(isinstance(long,totalRunLength))
        assert(isinstance(long,totalWeights))
        return totalRunlength / totalWeights

def addOrUpdateBridgeHistory(bridge, timestamp):
    with bridgedb.Storage.getDB() as db:
        bhe = db.getBridgeHistory(bridge.fingerprint)
        if not bhe:
            # This is the first status, assume 60 minutes.
            secondsSinceLastStatusPublication = 60*60
            lastSeenWithDifferentAddressAndPort = timestamp * 1000
            lastSeenWithThisAddressAndPort = timestamp * 1000
    
            bhe = BridgeHistory(
                    bridge.fingerprint, bridge.address, bridge.orPort,
                    0,#weightedUptime
                    0,#weightedTime
                    0,#weightedRunLength
                    0,# totalRunWeights
                    lastSeenWithDifferentAddressAndPort, # first timestamnp
                    lastSeenWithThisAddressAndPort,
                    0,#lastDiscountedHistoryValues,
                    0,#lastUpdatedWeightedTime
                    )
            # first time we have seen this descriptor
            db.updateIntoBridgeHistory(bhe)
        # Calculate the seconds since the last parsed status.  If this is
        # the first status or we haven't seen a status for more than 60
        # minutes, assume 60 minutes.
        statusPublicationMillis = timestamp * 1000
        if (statusPublicationMillis - bhe.lastSeenWithThisAddressAndPort) > 60*60*1000:
            secondsSinceLastStatusPublication = 60*60
            logging.debug("Capping secondsSinceLastStatusPublication to 1 hour")
        # otherwise, roll with it
        else:
            secondsSinceLastStatusPublication = \
                    (statusPublicationMillis - bhe.lastSeenWithThisAddressAndPort)/1000
        if secondsSinceLastStatusPublication <= 0 and bhe.weightedTime > 0:
            # old descriptor, bail
            logging.warn("Received old descriptor for bridge %s with timestamp %d",
                    bhe.fingerprint, statusPublicationMillis/1000)
            return bhe
    
        # iterate over all known bridges and apply weighting factor
        discountAndPruneBridgeHistories(statusPublicationMillis)

        # Update the weighted times of bridges
        updateWeightedTime(statusPublicationMillis)

        # For Running Bridges only:
        # compare the stored history against the descriptor and see if the
        # bridge has changed its address or port
        bhe = db.getBridgeHistory(bridge.fingerprint)

        if not bridge.running:
            logging.info("%s is not running" % bridge.fingerprint)
            return bhe

        # Parse the descriptor and see if the address or port changed
        # If so, store the weighted run time
        if bridge.orport != bhe.port or bridge.ip != bhe.ip:
            bhe.totalRunWeights += 1.0;
            bhe.weightedRunLength += bhe.tosa
            bhe.lastSeenWithDifferentAddressAndPort =\
                    bhe.lastSeenWithThisAddressAndPort

        # Regardless of whether the bridge is new, kept or changed
        # its address and port, raise its WFU times and note its
        # current address and port, and that we saw it using them.
        bhe.weightedUptime += secondsSinceLastStatusPublication
        bhe.lastSeenWithThisAddressAndPort = statusPublicationMillis
        bhe.ip = str(bridge.ip)
        bhe.port = bridge.orport
        return db.updateIntoBridgeHistory(bhe)

def discountAndPruneBridgeHistories(discountUntilMillis):
    with bridgedb.Storage.getDB() as db:
        bhToRemove = []
        bhToUpdate = []

        for bh in db.getAllBridgeHistory():
            # discount previous values by factor of 0.95 every 12 hours
            bh.discountWeightedFractionalUptimeAndWeightedTime(discountUntilMillis)
            # give the thing at least 24 hours before pruning it
            if bh.weightedFractionalUptime < 1 and bh.weightedTime > 60*60*24:
                logging.debug("Removing bridge from history: %s" % bh.fingerprint)
                bhToRemove.append(bh.fingerprint)
            else:
                bhToUpdate.append(bh)

        for k in bhToUpdate: db.updateIntoBridgeHistory(k)
        for k in bhToRemove: db.delBridgeHistory(k)

def updateWeightedTime(statusPublicationMillis):
    bhToUpdate = []
    with bridgedb.Storage.getDB() as db:
        for bh in db.getBridgesLastUpdatedBefore(statusPublicationMillis):
            interval = (statusPublicationMillis - bh.lastUpdatedWeightedTime)/1000
            if interval > 0:
                bh.weightedTime += min(3600,interval) # cap to 1hr
                bh.lastUpdatedWeightedTime = statusPublicationMillis
                #db.updateIntoBridgeHistory(bh)
                bhToUpdate.append(bh)

        for bh in bhToUpdate:
            db.updateIntoBridgeHistory(bh)

def updateBridgeHistory(bridges, timestamps):
    """Process all the timestamps and update the bridge stability statistics in
    the database.

    .. warning: This function is extremely expensive, and will keep getting
        more and more expensive, on a linearithmic scale, every time it is
        called. Blame the :mod:`bridgedb.Stability` module.

    :param dict bridges: All bridges from the descriptors, parsed into
        :class:`bridgedb.bridges.Bridge`s.
    :param dict timestamps: A dictionary whose keys are bridge fingerprints,
        and whose values are lists of integers, each integer being a timestamp
        (in seconds since Unix Epoch) for when a descriptor for that bridge
        was published.
    :rtype: dict
    :returns: The original **timestamps**, but which each list of integers
        (re)sorted.
    """
    logging.debug("Beginning bridge stability calculations")
    sortedTimestamps = {}

    for fingerprint, stamps in timestamps.items():
        stamps.sort()
        bridge = bridges[fingerprint]
        for timestamp in stamps:
            logging.debug(
                ("Adding/updating timestamps in BridgeHistory for %s in "
                 "database: %s") % (fingerprint, timestamp))
            timestamp = toUnixSeconds(timestamp.timetuple())
            addOrUpdateBridgeHistory(bridge, timestamp)
        # Replace the timestamps so the next sort is (hopefully) less
        # expensive:
        sortedTimestamps[fingerprint] = stamps

    logging.debug("Stability calculations complete")
    return sortedTimestamps
