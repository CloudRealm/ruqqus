import time
import calendar
from flask import *
from ruqqus.classes import *
from ruqqus.helpers.wrappers import *
from ruqqus.helpers.base36 import *
from secrets import token_hex
import matplotlib.pyplot as plt

from ruqqus.__main__ import db, app
from os import remove
@app.route("/api/ban_user/<user_id>", methods=["POST"])
@admin_level_required(3)
@validate_formkey
def ban_user(user_id, v):

    user=db.query(User).filter_by(id=user_id).first()

    if not user:
        abort(400)

    user.is_banned=v.id
    user.ban_reason=request.form.get("reason","")

    db.add(user)
    user.del_profile()
    user.del_banner()

    for a in user.alts:
        user.is_banned=v.id
        user.ban_reason=request.form.get("reason","")
        user.del_profile()
        user.del_banner()
        db.add(a)
        
    db.commit()
    
    return (redirect(user.url), user)

@app.route("/api/unban_user/<user_id>", methods=["POST"])
@admin_level_required(3)
@validate_formkey
def unban_user(user_id, v):

    user=db.query(User).filter_by(id=user_id).first()

    if not user:
        abort(400)

    user.is_banned=0

    db.add(user)
    db.commit()
    
    return (redirect(user.url), user)

@app.route("/api/ban_post/<post_id>", methods=["POST"])
@admin_level_required(3)
@validate_formkey
def ban_post(post_id, v):

    post=db.query(Submission).filter_by(id=base36decode(post_id)).first()

    if not post:
        abort(400)

    post.is_banned=True
    post.is_approved=0
    post.approved_utc=0
    post.stickied=False
    post.ban_reason=request.form.get("reason",None)

    db.add(post)
    db.commit()
    
    return (redirect(post.permalink), post)

@app.route("/api/unban_post/<post_id>", methods=["POST"])
@admin_level_required(3)
@validate_formkey
def unban_post(post_id, v):

    post=db.query(Submission).filter_by(id=base36decode(post_id)).first()

    if not post:
        abort(400)

    post.is_banned=False
    post.is_approved = v.id
    post.approved_utc=int(time.time())

    db.add(post)
    db.commit()
    
    return (redirect(post.permalink), post)


##@app.route("/api/promote/<user_id>/<level>", methods=["POST"])
##@admin_level_required(3)
##@validate_formkey
##def promote(user_id, level, v):
##
##    u = db.query(User).filter_by(id=user_id).first()
##    if not u:
##        abort(404)
##
##    max_level_involved = max(level, u.admin_level)
##
##    try:
##        admin_level_needed={1:3, 2:3, 3:5, 4:5, 5:6}[max_level_involved]
##    except KeyError:
##        abort(400)
##
##    if v.admin_level < admin_level_needed:
##        abort(403)
##
##    u.admin_level=level
##
##    db.add(u)
##    db.commit()
##
##    return redirect(u.url)
    
    
@app.route("/api/distinguish/<post_id>", methods=["POST"])
@admin_level_required(1)
@validate_formkey
def api_distinguish_post(post_id, v):

    post=db.query(Submission).filter_by(id=base36decode(post_id)).first()

    if not post:
        abort(404)

    if not post.author_id == v.id:
        abort(403)

    if post.distinguish_level:
        post.distinguish_level=0
    else:
        post.distinguish_level=v.admin_level

    db.add(post)
    db.commit()

    return (redirect(post.permalink), post)

@app.route("/api/sticky/<post_id>", methods=["POST"])
@admin_level_required(3)
def api_sticky_post(post_id, v):

    
    post=db.query(Submission).filter_by(id=base36decode(post_id)).first()
    if post:
        if post.stickied:
            post.stickied=False
            db.add(post)
            db.commit()
            return redirect(post.permalink)

    already_stickied=db.query(Submission).filter_by(stickied=True).first()

    post.stickied=True
    
    if already_stickied:
        already_stickied.stickied=False
        db.add(already_stickied)
        
    db.add(post)
    db.commit()

    return (redirect(post.permalink), post)

@app.route("/api/ban_comment/<c_id>", methods=["post"])
@admin_level_required(1)
def api_ban_comment(c_id, v):

    comment = db.query(Comment).filter_by(id=base36decode(c_id)).first()
    if not comment:
        abort(404)

    comment.is_banned=True
    comment.is_approved=0
    comment.approved_utc=0

    db.add(comment)
    db.commit()

    return "", 204

@app.route("/api/unban_comment/<c_id>", methods=["post"])
@admin_level_required(1)
def api_unban_comment(c_id, v):

    comment = db.query(Comment).filter_by(id=base36decode(c_id)).first()
    if not comment:
        abort(404)

    comment.is_banned=False
    comment.is_approved=v.id
    comment.approved_utc=int(time.time())

    db.add(comment)
    db.commit()

    return "", 204

@app.route("/api/distinguish_comment/<c_id>", methods=["post"])
@admin_level_required(1)
def api_distinguish_comment(c_id, v):

    comment = db.query(Comment).filter_by(id=base36decode(c_id)).first()
    if not comment:
        abort(404)

    comment.distinguish_level=v.admin_level

    db.add(comment)
    db.commit()

    return "", 204

@app.route("/api/undistinguish_comment/<c_id>", methods=["post"])
@admin_level_required(1)
def api_undistinguish_comment(c_id, v):

    comment = db.query(Comment).filter_by(id=base36decode(c_id)).first()
    if not comment:
        abort(404)

    comment.distinguish_level=0

    db.add(comment)
    db.commit()

    return "", 204


@app.route("/api/ban_guild/<bid>", methods=["POST"])
@admin_level_required(4)
@validate_formkey
def api_ban_guild(v, bid):

    board = get_board(bid)

    board.is_banned=True
    board.ban_reason=request.form.get("reason","")
    
    db.add(board)
    db.commit()

    return redirect(board.permalink)

@app.route("/api/unban_guild/<bid>", methods=["POST"])
@admin_level_required(4)
@validate_formkey
def api_unban_guild(v, bid):

    board = get_board(bid)

    board.is_banned=False
    board.ban_reason=""
    
    db.add(board)
    db.commit()

    return redirect(board.permalink)

@app.route("/api/mod_self/<bid>", methods=["POST"])
@admin_level_required(4)
@validate_formkey
def mod_self_to_guild(v, bid):

    board=get_board(bid)
    if not board.has_mod(v):
        mr = ModRelationship(user_id=v.id,
                             board_id=board.id,
                             accepted=True)
        db.add(mr)
        db.commit()

    return redirect(f"/+{board.name}/mod/mods")
        

@app.route("/api/user_stat_data", methods=['GET'])
#@cache.memoize
@admin_level_required(2)
def user_stat_data(v):

    days=int(request.args.get("days",14))

    now=time.gmtime()
    midnight_this_morning=time.struct_time((now.tm_year,
                                            now.tm_mon,
                                            now.tm_mday,
                                            0,
                                            0,
                                            0,
                                            now.tm_wday,
                                            now.tm_yday,
                                            0)
                                           )
    today_cutoff=calendar.timegm(midnight_this_morning)


    day = 3600*24

    day_cutoffs = [today_cutoff - day*i for i in range(days)]
    day_cutoffs.insert(0,calendar.timegm(now))

    daily_signups = [{"date":time.strftime("%d %b %Y", time.gmtime(day_cutoffs[i+1])),
                      "day_start":day_cutoffs[i+1],
                      "signups": db.query(User).filter(User.created_utc<day_cutoffs[i],
                                                       User.created_utc>day_cutoffs[i+1]
                                                       ).count()
                      } for i in range(len(day_cutoffs)-1)
                      ]

    

    
    user_stats = {'current_users':db.query(User).filter_by(is_banned=0, reserved=None).count(),
                  'banned_users': db.query(User).filter(User.is_banned!=0).count(),
                  'reserved_users':db.query(User).filter(User.reserved!=None).count(),
                  'email_verified_users':db.query(User).filter_by(is_banned=0, is_activated=True).count(),
                  'real_id_verified_users':db.query(User).filter(User.reserved!=None, User.real_id!=None).count()
                  }

    post_stats = [{"date":time.strftime("%d %b %Y", time.gmtime(day_cutoffs[i+1])),
                      "day_start":day_cutoffs[i+1],
                      "posts": db.query(Submission).filter(Submission.created_utc<day_cutoffs[i],
                                                           Submission.created_utc>day_cutoffs[i+1]
                                                           ).count()
                      } for i in range(len(day_cutoffs)-1)
                      ]

    guild_stats = [{"date": time.strftime("%d %b %Y", time.gmtime(day_cutoffs[i + 1])),
                   "day_start": day_cutoffs[i + 1],
                   "members": db.query(Board).filter(Board.created_utc < day_cutoffs[i],
                                                        Board.created_utc > day_cutoffs[i + 1]
                                                        ).count()
                   } for i in range(len(day_cutoffs) - 1)
                  ]

    comment_stats = [{"date": time.strftime("%d %b %Y", time.gmtime(day_cutoffs[i + 1])),
                   "day_start": day_cutoffs[i + 1],
                   "comments": db.query(Comment).filter(Comment.created_utc < day_cutoffs[i],
                                                        Comment.created_utc > day_cutoffs[i + 1]
                                                        ).count()
                   } for i in range(len(day_cutoffs) - 1)
                  ]

    vote_stats = [{"date": time.strftime("%d %b %Y", time.gmtime(day_cutoffs[i + 1])),
                      "day_start": day_cutoffs[i + 1],
                      "votes": db.query(Vote).filter(Vote.created_utc < day_cutoffs[i],
                                                           Vote.created_utc > day_cutoffs[i + 1]
                                                           ).count()
                      } for i in range(len(day_cutoffs) - 1)
                     ]

    #return jsonify(final)

    x=create_plot(sign_ups={'daily_signups':daily_signups},
                  guilds={'guild_stats':guild_stats},
                  posts={'post_stats':post_stats},
                  comments={'comment_stats':comment_stats},
                  votes={'vote_stats':vote_stats}
                  )

    final={"user_stats":user_stats,
           "signup_data":daily_signups,
           "post_data":post_stats,
           "guild_data":guild_stats,
           "comment_data":comment_stats,
           "vote_data":vote_stats,
           "plot":f"https://i.ruqqus.com/{x}"
           }
    
    return jsonify(final)


def create_plot(**kwargs):

    if not kwargs:
        return  abort(400)

    #create multiple charts
    daily_signups = [d["signups"] for d in kwargs["sign_ups"]['daily_signups']]
    guild_stats = [d["members"] for d in kwargs["guilds"]['guild_stats']]
    post_stats = [d["posts"] for d in kwargs["posts"]['post_stats']]
    comment_stats = [d["comments"] for d in kwargs["comments"]['comment_stats']]
    vote_stats = [d["votes"] for d in kwargs["votes"]['vote_stats']]
    daily_times = [d["day_start"] for d in kwargs["sign_ups"]['daily_signups']]

    multiple_plots(sign_ups=daily_signups,
                   guilds=guild_stats,
                   posts=post_stats,
                   comments=comment_stats,
                   votes=vote_stats,
                   daily_times=daily_times)

    # create single chart
    plt.legend(loc='upper left', frameon=True)

    plt.xlabel("Time")
    plt.ylabel("Growth")

    plt.plot(daily_times, daily_signups,color='red', label="Users")
    plt.plot(daily_times, guild_stats, color='blue', label="Guild Members")
    plt.plot(daily_times, post_stats, color='green', label="Posts")
    plt.plot(daily_times, comment_stats, color='gold', label="Comments")
    plt.plot(daily_times, vote_stats, color='silver', label="Vote")
    plt.legend()
    plt.savefig('plot2.png')

    #now=int(time.time())
    
    name=f"plot2.png"#_{now}.png"
    #aws.delete_file(name)
    aws.upload_from_file(name, "plot2.png")

    return name


def multiple_plots(**kwargs):

    #create multiple charts
    signup_chart = plt.subplot2grid((10,2), (0,0), rowspan=4, colspan=2)
    guilds_chart = plt.subplot2grid((10,2), (4,0), rowspan=3, colspan=1)
    posts_chart = plt.subplot2grid((10, 2), (4, 1), rowspan=3, colspan=1)
    comments_chart = plt.subplot2grid((10, 2), (7, 0), rowspan=3, colspan=1)
    votes_chart = plt.subplot2grid((10, 2), (7, 1), rowspan=3, colspan=1)

    signup_chart.plot(kwargs['daily_times'], kwargs['sign_ups'], color='red', label="Users")
    guilds_chart.plot(kwargs['daily_times'], kwargs['guilds'], color='blue', label="Guilds")
    posts_chart.plot(kwargs['daily_times'], kwargs['posts'], color='blue', label="Guilds")
    comments_chart.plot(kwargs['daily_times'], kwargs['comments'], color='blue', label="Guilds")
    votes_chart.plot(kwargs['daily_times'], kwargs['votes'], color='blue', label="Guilds")

    signup_chart.set_ylabel("Signups")
    guilds_chart.set_ylabel("Joins")
    posts_chart.set_ylabel("Posts")
    comments_chart.set_ylabel("Comments")
    votes_chart.set_ylabel("Votes")
    comments_chart.set_xlabel("Time (UTC)")
    votes_chart.set_xlabel("Time (UTC)")
    plt.legend()

    plt.savefig('plot3.png')
    plt.clf()
    # now=int(time.time())

    name = f"plot3.png"  # _{now}.png"
    # aws.delete_file(name)
    aws.upload_from_file(name, "plot3.png")
    return name