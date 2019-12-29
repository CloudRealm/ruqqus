from flask import *
import ruqqus.classes
from ruqqus.classes import *
from ruqqus.helpers.wrappers import *
from ruqqus.helpers.security import *
from ruqqus.helpers.sanitize import *
from ruqqus.mail import *
from ruqqus.__main__ import db, app

@app.route("/settings/profile", methods=["POST"])
@is_not_banned
@validate_formkey
def settings_profile_post(v):

    updated=False

    if request.form.get("new_password"):
        if request.form.get("new_password") != request.form.get("cnf_password"):
            return render_template("settings.html", v=v, error="Passwords do not match.")

        if not v.verifyPass(request.form.get("old_password")):
            return render_template("settings.html", v=v, error="Incorrect password")

        v.passhash=v.hash_password(request.form.get("new_password"))
        updated=True
                                  

    if request.form.get("over18") != v.over_18:
        updated=True
        v.over_18=bool(request.form.get("over18", None))

    if request.form.get("bio") != v.bio:
        updated=True
        bio = request.form.get("bio")[0:256]
        v.bio=bio

        v.bio_html=sanitize(bio)


    x=int(request.form.get("title_id",0))
    if x==0:
        v.title_id=None
        updated=True
    elif x>0:
        title =get_title(x)
        if bool(eval(title.qualification_expr)):
            v.title_id=title.id
            updated=True
        else:
            return render_template("settings_profile.html",
                                   v=v,
                                   error=f"Unable to set title {title.text} - {title.requirement_string}"
                                   )
    else:
        abort(400)
        
    if updated:
        db.add(v)
        db.commit()

        return render_template("settings_profile.html",
                               v=v,
                               msg="Your settings have been saved."
                               )

    else:
        return render_template("settings_profile.html",
                               v=v,
                               error="You didn't change anything."
                               )

@app.route("/settings/security", methods=["POST"])
@is_not_banned
@validate_formkey
def settings_security_post(v):

    if request.form.get("new_password"):
        if request.form.get("new_password") != request.form.get("cnf_password"):
            return render_template("settings_security.html", v=v, error="Passwords do not match.")

        if not v.verifyPass(request.form.get("old_password")):
            return render_template("settings_security.html", v=v, error="Incorrect password")

        v.passhash=v.hash_password(request.form.get("new_password"))

        db.add(v)
        db.commit()
        
        return render_template("settings_security.html", v=v, msg="Your password has been changed.")

    if request.form.get("new_email"):

        if not v.verifyPass(request.form.get('password')):
            return render_template("settings_security.html", v=v, error="Invalid password"), 401
            
        
        new_email = request.form.get("new_email")
        if new_email == v.email:
            return render_template("settings_security.html", v=v, error="That's already your email!")


        url=f"https://{environ.get('domain')}/activate"
            
        now=int(time.time())

        token=generate_hash(f"{new_email}+{v.id}+{now}")
        params=f"?email={quote(new_email)}&id={v.id}&time={now}&token={token}"

        link=url+params
        
        send_mail(to_address=new_email,
                  subject="Verify your email address.",
                  html=render_template("email/email_change.html",
                                       action_url=link,
                                       v=v)
                  )
        return render_template("settings_security.html", v=v, msg=f"Verify your new email address {new_email} to complete the email change process.")
        

@app.route("/settings/dark_mode/<x>", methods=["POST"])
@auth_required
@validate_formkey
def settings_dark_mode(x, v):

    try:
        x=int(x)
    except:
        abort(400)

    if x not in [0,1]:
        abort(400)

    if not v.referral_count:
        session["dark_mode_enabled"]=False
        abort(403)
    else:
        session["dark_mode_enabled"]=bool(x)
        return "",204
        
@app.route("/settings/log_out_all_others", methods=["POST"])
@auth_required
@validate_formkey
def settings_log_out_others(v):

    submitted_password=request.form.get("password","")

    if not v.verifyPass(submitted_password):
        return render_template("settings_security.html", v=v, error="Incorrect Password"), 401

    #increment account's nonce
    v.login_nonce +=1

    #update cookie accordingly
    session["login_nonce"]=v.login_nonce

    db.add(v)
    db.commit()

    return render_template("settings_security.html", v=v, msg="All other devices have been logged out")



@app.route("/settings/images/profile", methods=["POST"])
@auth_required
@validate_formkey
def settings_images_profile(v):

    v.set_profile(request.files["profile"])

    return render_template("settings_profile.html", v=v, msg="Profile picture successfully updated.")

@app.route("/settings/images/banner", methods=["POST"])
@auth_required
@validate_formkey
def settings_images_banner(v):

    v.set_banner(request.files["banner"])

    return render_template("settings_profile.html", v=v, msg="Banner successfully updated.")


@app.route("/settings/delete/profile", methods=["POST"])
@auth_required
@validate_formkey
def settings_delete_profile(v):

    v.del_profile()

    return render_template("settings_profile.html", v=v, msg="Profile picture successfully removed.")

@app.route("/settings/delete/banner", methods=["POST"])
@auth_required
@validate_formkey
def settings_delete_banner(v):

    v.del_banner()

    return render_template("settings_profile.html", v=v, msg="Banner successfully removed.")





