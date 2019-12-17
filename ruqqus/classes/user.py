from werkzeug.security import generate_password_hash, check_password_hash
from flask import render_template, session, request
from time import strftime, time, gmtime
from sqlalchemy import *
from sqlalchemy.orm import relationship, deferred
from os import environ
from secrets import token_hex
import random

from ruqqus.helpers.base36 import *
from ruqqus.helpers.security import *
from ruqqus.helpers.lazy import lazy
from .votes import Vote
from .alts import Alt
from .submission import Submission
from ruqqus.__main__ import Base, db, cache

class User(Base):

    __tablename__="users"
    id = Column(Integer, primary_key=True)
    username = Column(String, default=None)
    email = Column(String, default=None)
    passhash = Column(String, default=None)
    created_utc = Column(BigInteger, default=0)
    admin_level = Column(Integer, default=0)
    is_activated = Column(Boolean, default=False)
    reddit_username = Column(String, default=None)
    over_18=Column(Boolean, default=False)
    creation_ip=Column(String, default=None)
    most_recent_ip=Column(String, default=None)
    submissions=relationship("Submission", lazy="dynamic", primaryjoin="Submission.author_id==User.id", backref="author_rel")
    comments=relationship("Comment", lazy="dynamic", primaryjoin="Comment.author_id==User.id")
    votes=relationship("Vote", lazy="dynamic", backref="users")
    commentvotes=relationship("CommentVote", lazy="dynamic", backref="users")
    bio=Column(String, default="")
    bio_html=Column(String, default="")
    badges=relationship("Badge", lazy="dynamic", backref="user")
    real_id=Column(String, default=None)
    notifications=relationship("Notification", lazy="dynamic", backref="user")
    referred_by=Column(Integer, default=None)
    is_banned=Column(Integer, default=0)
    ban_reason=Column(String, default="")

    moderates=relationship("ModRelationship", lazy="dynamic")
    banned_from=relationship("BanRelationship", lazy="dynamic", primaryjoin="BanRelationship.user_id==User.id")
    subscriptions=relationship("Subscription", lazy="dynamic")

    following=relationship("Follow", lazy="dynamic", primaryjoin="Follow.user_id==User.id")
    followers=relationship("Follow", lazy="dynamic", primaryjoin="Follow.target_id==User.id")


    
    #properties defined as SQL server-side functions
    energy = deferred(Column(Integer, server_default=FetchedValue()))
    referral_count=deferred(Column(Integer, server_default=FetchedValue()))
    follower_count=deferred(Column(Integer, server_default=FetchedValue()))



    def __init__(self, **kwargs):

        if "password" in kwargs:

            kwargs["passhash"]=self.hash_password(kwargs["password"])
            kwargs.pop("password")

        kwargs["created_utc"]=int(time())

        super().__init__(**kwargs)
        
    @cache.memoize(timeout=600)
    def idlist(self, sort="hot", page=1, kind="board"):

        

        posts=db.query(Submission).filter_by(is_banned=False,
                                             is_deleted=False,
                                             stickied=False
                                             )
        if kind=="board":
            board_ids=[x.board_id for x in self.subscriptions]
            posts=posts.filter(Submission.board_id.in_(board_ids))
        elif kind=="user":
            user_ids=[x.target_id for x in self.following.all()]
            posts=posts.filter(Submission.author_id.in_(user_ids))
        else:
            abort(422)

        if not self.over_18:
            posts=posts.filter_by(over_18=False)
            

        if sort=="hot":
            posts=posts.order_by(text("submissions.rank_hot desc"))
        elif sort=="new":
            posts=posts.order_by(Submission.created_utc.desc())
        elif sort=="disputed":
            posts=posts.order_by(text("submissions.rank_fiery desc"))
        elif sort=="top":
            posts=posts.order_by(text("submissions.score desc"))
        elif sort=="activity":
            posts=posts.order_by(text("submissions.rank_activity desc"))
        else:
            abort(422)

        posts=[x.id for x in posts.offset(25*(page-1)).limit(26).all()]

        return posts

    def list_of_posts(self, ids):

        next_exists=(len(ids)==26)
        ids=ids[0:25]

        if ids:

            #assemble list of tuples
            i=1
            tups=[]
            for x in ids:
                tups.append((x,i))
                i+=1

            tups=str(tups).lstrip("[").rstrip("]")

            #hit db for entries
            posts=db.query(Submission
                           ).from_statement(
                               text(
                               f"""
                                select submissions.*, submissions.ups, submissions.downs
                                from submissions
                                join (values {tups}) as x(id, n) on submissions.id=x.id
                                order by x.n"""
                               )).all()
        else:
            posts=[]

        return posts, next_exists

    def rendered_follow_page(self, sort="hot", page=1):

        ids=self.idlist(sort=sort, page=page, kind="user")

        posts, next_exists = self.list_of_posts(ids)

        return render_template("follows.html", v=self, listing=posts, next_exists=next_exists, sort_method=sort, page=page)

    def rendered_subscription_page(self, sort="hot", page=1):

        ids=self.idlist(sort=sort, page=page, kind="board")

        posts, next_exists = self.list_of_posts(ids)

        return render_template("subscriptions.html", v=self, listing=posts, next_exists=next_exists, sort_method=sort, page=page)        

    


    @property
    def boards_modded(self):

        return [x.board for x in self.moderates.order_by(text("name asc")).all()]

    @property
    @cache.memoize(timeout=3600) #1hr cache time for user rep
    def karma(self):
        return self.energy


    @property
    def base36id(self):
        return base36encode(self.id)

    @property
    def fullname(self):
        return f"t1_{self.base36id}"

    @property
    def banned_by(self):

        if not self.is_banned:
            return None

        return db.query(User).filter_by(id=self.is_banned).first()
    
    def vote_status_on_post(self, post):

        vote = self.votes.filter_by(submission_id=post.id).first()
        if not vote:
            return 0
        
        return vote.vote_type


    def vote_status_on_comment(self, comment):

        vote = self.commentvotes.filter_by(comment_id=comment.id).first()
        if not vote:
            return 0
        
        return vote.vote_type
    

    def hash_password(self, password):
        return generate_password_hash(password, method='pbkdf2:sha512', salt_length=8)

    def verifyPass(self, password):
        return check_password_hash(self.passhash, password)
        
    def rendered_userpage(self, v=None):

        if self.is_banned and (not v or v.admin_level < 3):
            return render_template("userpage_banned.html", u=self, v=v)

        page=int(request.args.get("page","1"))
        page=max(page, 1)

        submissions=self.submissions

        if not (v and v.over_18):
            submissions=submissions.filter_by(over_18=False)

        if not (v and (v.admin_level >=3)):
            submissions=submissions.filter_by(is_deleted=False)

        if not (v and (v.admin_level >=3 or v.id==self.id)):
            submissions=submissions.filter_by(is_banned=False)

        listing = [x for x in submissions.order_by(text("created_utc desc")).offset(25*(page-1)).limit(26)]
        
        #we got 26 items just to see if a next page exists
        next_exists=(len(listing)==26)
        listing=listing[0:25]

        is_following=(v and self.has_follower(v))

        return render_template("userpage.html",
                               u=self,
                               v=v,
                               listing=listing,
                               page=page,
                               next_exists=next_exists,
                               is_following=is_following)

    def rendered_comments_page(self, v=None):

        if self.is_banned and (not v or v.admin_level < 3):
            return render_template("userpage_banned.html", u=self, v=v)
        
        page=int(request.args.get("page","1"))

        comments=self.comments

        if not (v and v.over_18):
            comments=comments.filter_by(over_18=False)
            
        if not (v and (v.admin_level >=3)):
            comments=comments.filter_by(is_deleted=False)
            
        if not (v and (v.admin_level >=3 or v.id==self.id)):
            comments=comments.filter_by(is_banned=False)
        

        listing=[ c for c in comments.order_by(text("created_utc desc")).offset(25*(page-1)).limit(26)]
        #we got 26 items just to see if a next page exists
        next_exists=(len(listing)==26)
        listing=listing[0:25]

        is_following=(v and self.has_follower(v))
        
        return render_template("userpage_comments.html",
                               u=self,
                               v=v,
                               listing=listing,
                               page=page,
                               next_exists=next_exists,
                               is_following=is_following)

    @property
    def formkey(self):

        if "session_id" not in session:
            session["session_id"]=token_hex(16)

        msg=f"{session['session_id']}{self.id}"

        return generate_hash(msg)

    def validate_formkey(self, formkey):

        return validate_hash(f"{session['session_id']}{self.id}", formkey)
    
    @property
    def url(self):
        return f"/@{self.username}"

    @property
    def permalink(self):
        return self.url

    @property
    @lazy
    def created_date(self):

        return strftime("%d %B %Y", gmtime(self.created_utc))

    def __repr__(self):
        return f"<User(username={self.username})>"


    @property
    @lazy
    def color(self):

        random.seed(f"{self.id}+{self.username}")

        R=random.randint(32, 223)
        G=random.randint(32, 223)
        B=random.randint(32, 223)
        

        return str(base_encode(R, 16))+str(base_encode(G, 16))+str(base_encode(B, 16))

    def notifications_page(self, page=1, include_read=False):

        page=int(page)

        notifications=self.notifications.filter_by(is_banned=False, is_deleted=False)

        if not include_read:
            notifications=notifications.filter_by(read=False)

        notifications = notifications.order_by(text("notifications.created_utc desc")).offset(25*(page-1)).limit(25)

        comments=[n.comment for n in notifications]

        for n in notifications:
            if not n.read:
                n.read=True
                db.add(n)
                db.commit()

        return render_template("notifications.html", v=self, notifications=comments)
    
    @property
    def notifications_count(self):

        return self.notifications.filter_by(read=False, is_banned=False, is_deleted=False).count()

    @property
    @cache.memoize(timeout=60)
    def post_count(self):

        return self.submissions.filter_by(is_banned=False).count()

    @property
    @cache.memoize(timeout=60) 
    def comment_count(self):

        return self.comments.filter_by(is_banned=False, is_deleted=False).count()

    @property
    #@cache.memoize(timeout=60)
    def badge_pairs(self):

        output=[]

        badges=[x for x in self.badges.all()]

        while badges:
            
            to_append=[badges.pop(0)]
            
            if badges:
                to_append.append(badges.pop(0))
                
            output.append(to_append)

        return output

    @property
    def alts(self):

        alts1=db.query(User).join(Alt, Alt.user2==User.id).filter(Alt.user1==self.id).all()
        alts2=db.query(User).join(Alt, Alt.user1==User.id).filter(Alt.user2==self.id).all()

        return list(set([x for x in alts1]+[y for y in alts2]))
        

    def has_follower(self, user):

        return self.followers.filter_by(user_id=user.id).first()
