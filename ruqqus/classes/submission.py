from flask import render_template, request, abort
import time
from sqlalchemy import *
from sqlalchemy.orm import relationship, deferred
import math
from urllib.parse import urlparse
import random
from os import environ
import requests
from .mix_ins import *
from ruqqus.helpers.base36 import *
from ruqqus.helpers.lazy import lazy
import ruqqus.helpers.aws as aws
from ruqqus.__main__ import Base, db, cache
from .votes import Vote
from .domains import Domain
from .flags import Flag
from .badwords import *
from .comment import Comment

class Submission(Base, Stndrd, Age_times, Scores, Fuzzing):
 
    __tablename__="submissions"

    id = Column(BigInteger, primary_key=True)
    author_id = Column(BigInteger, ForeignKey("users.id"))
    title = Column(String(500), default=None)
    url = Column(String(500), default=None)
    edited_utc = Column(BigInteger, default=0)
    created_utc = Column(BigInteger, default=0)
    is_banned = Column(Boolean, default=False)
    is_deleted=Column(Boolean, default=False)
    distinguish_level=Column(Integer, default=0)
    created_str=Column(String(255), default=None)
    stickied=Column(Boolean, default=False)
    comments=relationship("Comment", lazy="dynamic", primaryjoin="Comment.parent_submission==Submission.id", backref="submissions")
    body=Column(String(10000), default="")
    body_html=Column(String(20000), default="")
    embed_url=Column(String(256), default="")
    domain_ref=Column(Integer, ForeignKey("domains.id"))
    flags=relationship("Flag", lazy="dynamic", backref="submission")
    is_approved=Column(Integer, ForeignKey("users.id"), default=0)
    approved_utc=Column(Integer, default=0)
    board_id=Column(Integer, ForeignKey("boards.id"), default=None)
    original_board_id=Column(Integer, ForeignKey("boards.id"), default=None)
    over_18=Column(Boolean, default=False)
    original_board=relationship("Board", lazy="subquery", primaryjoin="Board.id==Submission.original_board_id")
    ban_reason=Column(String(128), default="")
    creation_ip=Column(String(64), default="")
    mod_approved=Column(Integer, default=None)
    accepted_utc=Column(Integer, default=0)
    is_image=Column(Boolean, default=False)
    has_thumb=Column(Boolean, default=False)
    post_public=Column(Boolean, default=True)
    score_hot=Column(Float, default=0)
    score_disputed=Column(Float, default=0)
    score_top=Column(Float, default=1)
    score_activity=Column(Float, default=0)
    author_name=Column(String(64), default="")
    guild_name=Column(String(64), default="")
    is_offensive=Column(Boolean, default=False)
    board=relationship("Board", lazy="joined", innerjoin=True, primaryjoin="Submission.board_id==Board.id")
    author=relationship("User", lazy="joined", innerjoin=True, primaryjoin="Submission.author_id==User.id")

    approved_by=relationship("User", uselist=False, primaryjoin="Submission.is_approved==User.id")


    #These are virtual properties handled as postgres functions server-side
    #There is no difference to SQLAlchemy, but they cannot be written to

    ups = deferred(Column(Integer, server_default=FetchedValue()))
    downs=deferred(Column(Integer, server_default=FetchedValue()))
    age=deferred(Column(Integer, server_default=FetchedValue()))
    comment_count=Column(Integer, server_default=FetchedValue())
    flag_count=deferred(Column(Integer, server_default=FetchedValue()))
    report_count=deferred(Column(Integer, server_default=FetchedValue()))
    score=Column(Float, server_default=FetchedValue())
    is_public=Column(Boolean, server_default=FetchedValue())

    rank_hot=deferred(Column(Float, server_default=FetchedValue()))
    rank_fiery=deferred(Column(Float, server_default=FetchedValue()))
    rank_activity=deferred(Column(Float, server_default=FetchedValue()))    

    def __init__(self, *args, **kwargs):

        if "created_utc" not in kwargs:
            kwargs["created_utc"]=int(time.time())
            kwargs["created_str"]=time.strftime("%I:%M %p on %d %b %Y", time.gmtime(kwargs["created_utc"]))

        kwargs["creation_ip"]=request.remote_addr

        super().__init__(*args, **kwargs)
        
    def __repr__(self):
        return f"<Submission(id={self.id})>"

    @property
    def board_base36id(self):
        return base36encode(self.board_id)


    @property
    #@cache.memoize(timeout=60)
    def domain_obj(self):
        if not self.domain_ref:
            return None
        
        return db.query(Domain).filter_by(id=self.domain_ref).first()


    @property
    @cache.memoize(timeout=60)
    def score_percent(self):
        try:
            return int((self.ups/(self.ups+self.downs))*100)
        except ZeroDivisionError:
            return 0


    @property
    def fullname(self):
        return f"t2_{self.base36id}"

    @property
    def permalink(self):
        return f"/post/{self.base36id}"

    @property
    def is_archived(self):

        now=int(time.time())

        cutoff=now-(60860*24*180)

        return self.created_utc < cutoff
                                      
    def rendered_page(self, comment=None, comment_info=None, v=None):

        #check for banned
        if self.is_deleted:
            template="submission_deleted.html"
        elif v and v.admin_level>=3:
            template="submission.html"
        elif self.is_banned:
            template="submission_banned.html"
        else:
            template="submission.html"

        private=not self.is_public and not self.board.can_view(v)

        
        if private and not self.author_id==v.id:
            abort(403)
        elif private:
            self.__dict__["replies"]=[]
        else:
            #load and tree comments
            #calling this function with a comment object will do a comment permalink thing
            self.tree_comments(comment=comment)
        
        #return template
        return render_template(template,
                               v=v,
                               p=self,
                               sort_method=request.args.get("sort","Hot").capitalize(),
                               linked_comment=comment,
                               comment_info=comment_info,
                               is_allowed_to_comment=self.board.can_comment(v)
                               )


    @property
    @lazy
    def domain(self):

        if not self.url:
            return "text post"
        domain= urlparse(self.url).netloc
        if domain.startswith("www."):
            domain=domain.split("www.")[1]
        return domain



    def tree_comments(self, comment=None):

        def tree_replies(thing, layer=1):

            thing.__dict__["replies"]=[]
            i=len(comments)-1
        
            while i>=0:
                if comments[i].parent_fullname==thing.fullname:
                    thing.__dict__["replies"].append(comments[i])
                    comments[i].__dict__["parent"]=thing
                    print(" "*layer+"-"+comments[i].base36id)
                    comments.pop(i)

                i-=1
                
            if layer <=8:
                for reply in thing.replies:
                    tree_replies(reply, layer=layer+1)
                
        ######
                
        if comment:
            self.replies=[comment]
            return



        #get sort type
        sort_type = request.args.get("sort","hot")


        #Treeing is done from the end because reasons, so these sort orders are reversed
        if sort_type=="hot":
            comments=self.comments.order_by(Comment.score_hot.asc()).all()
        elif sort_type=="top":
            comments=self.comments.order_by(Comment.score_top.asc()).all()
        elif sort_type=="new":
            comments=self.comments.order_by(Comment.created_utc.desc()).all()
        elif sort_type=="disputed":
            comments=self.comments.order_by(Comment.score_disputed.asc()).all()
        elif sort_type=="random":
            c=self.comments.all()
            comments=random.sample(c, k=len(c))
        else:
            abort(422)


        print(f'treeing {len(comments)} comments')
        tree_replies(self)

        


    @property
    def active_flags(self):
        if self.is_approved:
            return 0
        else:
            return self.flags.filter(Flag.created_utc>self.approved_utc).count()

    @property
    def active_reports(self):
        if self.mod_approved:
            return 0
        else:
            return self.reports.filter(Report.created_utc>self.accepted_utc).count()


    @property
    #@lazy
    def thumb_url(self):
    
        if self.domain=="i.ruqqus.com":
            return self.url
        elif self.has_thumb:
            return f"https://i.ruqqus.com/posts/{self.base36id}/thumb.png"
        elif self.is_image:
            return self.url
        else:
            return None

    def visibility_reason(self, v):

        if self.author_id==v.id:
            return "this is your content."
        elif self.board.has_mod(v):
            return f"you are a guildmaster of +{self.board.name}."
        elif self.board.has_contributor(v):
            return f"you are an approved contributor in +{self.board.name}."
        elif v.admin_level >= 4:
            return "you are a Ruqqus admin."


    def determine_offensive(self):

        for x in db.query(BadWord).all():
            if (self.body and x.check(self.body)) or x.check(self.title):
                self.is_offensive=True
                db.commit()
                break
        else:
            self.is_offensive=False
            db.commit()


    @property
    def json(self):

        if self.is_banned:
            return {'is_banned':True,
                    'is_deleted':self.is_deleted,
                    'ban_reason': self.ban_reason,
                    'id':self.base36id,
                    'title':self.title,
                    'permalink':self.permalink,
                    'guild_name':self.guild_name
                    }
        elif self.is_deleted:
            return {'is_banned':bool(self.is_banned),
                    'is_deleted':True,
                    'id':self.base36id,
                    'title':self.title,
                    'permalink':self.permalink,
                    'guild_name':self.guild_name
                    }
        return {'author':self.author_name,
                'permalink':self.permalink,
                'is_banned':False,
                'is_deleted':False,
                'created_utc':self.created_utc,
                'id':self.base36id,
                'title':self.title,
                'is_nsfw':self.over_18,
                'is_offensive':self.is_offensive,
                'thumb_url':self.thumb_url,
                'domain':self.domain,
                'is_archived':self.is_archived,
                'url':self.url,
                'body':self.body,
                'body_html':self.body_html,
                'created_utc':self.created_utc,
                'edited_utc':self.edited_utc,
                'guild_name':self.guild_name,
                'embed_url':self.embed_url
                }
