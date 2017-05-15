#!/usr/bin/python
# -*- coding: utf-8 -*-
import rospy
from tms_ur_listener.msg import julius_msg
from std_msgs.msg import Bool
from std_msgs.msg import String
from janome.tokenizer import Tokenizer
from tms_msg_db.msg import Tmsdb
from tms_msg_db.srv import TmsdbGetData
from tms_msg_ts.srv import ts_req
import time

trigger = ['スマートパル','見守る君','TMS']
error_msg1 = "すみません。聞き取れませんでした。"
error_msg2 = "エラーが発生したため、処理を中断します"
sid = 100000

class TmsUrListener():
    def __init__(self):
        rospy.init_node("tms_ur_listener")
        rospy.on_shutdown(self.shutdown)
        rospy.Subscriber("julius_msg",julius_msg,self.callback)
        self.power_pub = rospy.Publisher("julius_power",Bool,queue_size=10)
        self.speaker_pub = rospy.Publisher("speaker",String,queue_size=10)
        self.t = Tokenizer()
        self.robot_name = ''
        print 'tms_ur_listener_server ready...'

    def julius_power(self,data):
        msg = Bool()
        msg.data = data
        self.power_pub.publish(msg)

    def speaker(self,data):
        speak = String()
        speak.data = data
        self.speaker_pub.publish(speak)

    def db_reader(self,data):
        target=Tmsdb()
        rospy.wait_for_service('tms_db_reader')
        try:
            tms_db_reader = rospy.ServiceProxy('tms_db_reader', TmsdbGetData)
            res = tms_db_reader(data)
            target = res.tmsdb[0]
            return target
        except rospy.ServiceException as e:
            print "Service call failed: %s" % e
            self.speaker(error_msg2)
            return None

    def tag_reader(self,data):
        temp_dbdata = Tmsdb()
        temp_dbdata.tag=data
        return self.db_reader(temp_dbdata)

    def callback(self, data):
        rospy.loginfo(data)
        if data.value >= 10.0: #google speech api
            rospy.loginfo("get command!")
            tokens = self.t.tokenize(data.data.decode('utf-8'))
            nouns = []
            verb = ''
            for token in tokens:
                print token
                if token.part_of_speech.split(',')[0] == u'動詞':
                    verb += token.base_form.encode('utf-8')
                elif token.part_of_speech.split(',')[0] == u'名詞':
                    nouns.append(token.base_form.encode('utf-8'))
            print str(nouns).decode('string-escape')
            print verb
            if self.robot_name == 'TMS': #tms function
                task_id = 0
                announce = ""
                for noun in nouns:
                    target = self.tag_reader(noun)
                    if target is None:
                        return
                    if target.type == 'task':
                        task_id = target.id
                        nouns.remove(noun)

                print task_id
                if task_id == 0:
                    self.speaker(error_msg1)
                    return
                if task_id == 8100: #search_object
                    object_id = 0
                    place_id = 0
                    object_name = ""
                    place_name = ""
                    for noun in nouns:
                        print noun
                        target = self.tag_reader(noun)
                        if target is None:
                            return
                        if target.type == 'object':
                            object_id = target.id
                            object_name = target.announce

                    temp_dbdata=Tmsdb()
                    temp_dbdata.id = object_id
                    temp_dbdata.state = 1
                    target = self.db_reader(temp_dbdata)
                    if target is None:
                        return
                    place_id = target.place

                    temp_dbdata=Tmsdb()
                    temp_dbdata.id = place_id + sid
                    target = self.db_reader(temp_dbdata)
                    if target is None:
                        return
                    place_name = target.announce

                    if object_name == "" or place_name == "":
                        self.speaker(error_msg1)
                        return

                    announce = object_name + "は、" + place_name + "にあります。"
                    print announce
                    self.speaker(announce)
                    time.sleep(5)
                    self.julius_power(True)

            else: #robot function
                if verb=='' or self.robot_name=='':
                    self.speaker(error_msg1)
                    return
                task_id = 0
                robot_id = 0
                object_id = 0
                user_id = 1100
                place_id = 0
                announce = ""
                robot_name = ""
                object_name = ""
                user_name = "太郎さん"
                place_name = ""

                target = self.tag_reader(verb)
                if target is None:
                    return
                task_id = target.id
                announce = target.announce

                target = self.tag_reader(self.robot_name)
                if target is None:
                    return
                robot_id = target.id
                robot_name = target.announce

                for noun in nouns:
                    target = self.tag_reader(noun)
                    if target is None:
                        return
                    if target.type == 'object':
                        object_id = target.id
                        object_name = target.announce
                    elif target.type == 'person':
                        user_id = target.id
                        user_name = target.announce
                    elif target.type == 'furniture':
                        place_id = target.id
                        place_name = target.announce

                anc_list = announce.split("$")
                announce = ""
                for anc in anc_list:
                    if anc == "robot":
                        if robot_id==0:
                            self.speaker(error_msg1)
                            return
                        announce += robot_name
                    elif anc == "object":
                        if object_id==0:
                            self.speaker(error_msg1)
                            return
                        announce += object_name
                    elif anc == "user":
                        if user_id==0:
                            self.speaker(error_msg1)
                            return
                        announce += user_name
                    elif anc == "place":
                        if place_id==0:
                            self.speaker(error_msg1)
                            return
                        announce += place_name
                    else:
                        announce += anc

                print announce
                self.speaker(announce)

                print 'send command'
                try:
                    rospy.wait_for_service('tms_ts_master', timeout=2.0)
                except rospy.ROSException:
                    print "tms_ts_master is not work"

                try:
                    tms_ts_master = rospy.ServiceProxy('tms_ts_master',ts_req)
                    res = tms_ts_master(0,task_id,robot_id,object_id,user_id,place_id,0)
                    print res
                except rospy.ServiceException as e:
                    print "Service call failed: %s" % e

                time.sleep(5)
                self.julius_power(True)

        elif data.value > 0.8: #Julius
            if data.data in trigger:
                rospy.loginfo("call robot name")
                rospy.loginfo("kill julius!!")
                self.robot_name = data.data
                self.julius_power(False)
                self.speaker("\sound1")

    def shutdown(self):
        rospy.loginfo("Stopping the node")

if __name__ == '__main__':
    try:
        TmsUrListener()
        rospy.spin()
    except rospy.ROSInterruptException:
        rospy.loginfo("tms_ur_listener node terminated.")