import datetime
from flask_cors import CORS
from flask import Flask, jsonify, redirect, request, Response, send_from_directory, session
from pymongo import MongoClient
from flask_pymongo import PyMongo
from werkzeug.security import generate_password_hash, check_password_hash
import json
import uuid
from bson import ObjectId
from datetime import datetime, timedelta
import logging
# from delteBoardemailConfirmation import send_mailForDeletinBoardHandler
from flask_mail import Mail, Message
from flask_socketio import SocketIO
from flask_socketio import join_room
from flask_socketio import leave_room
from flask_socketio import rooms
from flask_socketio import send
# from flask_socketio import emit
from flask_socketio import emit
from pymongo import UpdateOne
import threading
import time
from werkzeug.utils import secure_filename
import cloudinary
from cloudinary.uploader import upload
from cloudinary.utils import cloudinary_url
from dotenv import load_dotenv
import os

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))
logging.basicConfig(filename="backendPYLogs.log", level=logging.INFO)
app = Flask(__name__)
cors_origins = os.getenv('CORS_ORIGINS').split(',')
CORS(app, origins=cors_origins)
CORS(app, resources={r"/upload": {"origins": os.getenv('CORS_UPLOAD_ORIGINS')}}, supports_credentials=True)

# Setup MongoDB client
mongo_uri = os.getenv('MONGO_URI')
client = MongoClient(mongo_uri)
db = client[os.getenv('MONGO_DB_NAME')]

# Setup Flask-Mail
mail = Mail(app)

# Setup Flask-SocketIO
socketio = SocketIO(app, cors_allowed_origins="*")

# Setup Cloudinary
cloudinary.config(
    cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
    api_key=os.getenv('CLOUDINARY_API_KEY'),
    api_secret=os.getenv('CLOUDINARY_API_SECRET')
)

editor_collection = db['editorData']

@app.route("/fetchUsersWorkspaces", methods=["POST"])
def fetchUsersWorkspaces():
    if request.method == "POST":
        requiredPayload = ["sub"]
        data = request.get_json()
        for item in requiredPayload:
            if item not in data.keys():
                return jsonify({"message": f"{item} was missing", "status": 400})
        try:
            foundUser = db["miroUsers"].find_one({"sub": data["sub"]})
            logging.info(f"Found user for fetch user workspaces: {foundUser}")
            if foundUser:
                foundUser["_id"] = str(foundUser["_id"])
                for workspace in foundUser["workspace_details"]:
                    if len(workspace["userBoards"]) > 0:
                        for board in workspace["userBoards"]:
                            if board.get("sharedBoard_id"):
                                board["sharedBoard_id"] = str(board["sharedBoard_id"])
                return jsonify({"message": "bothExist", "status": 200, "data": foundUser})
            else:
                return jsonify({"message": "User not found", "status": 404}), 404
        except Exception as error:
            logging.error(f"Exception black operation failed: {error}")
            return jsonify({"message": "FAILURE", "status": 400}), 400

@app.route("/userOnBoarding", methods=["POST"])
def handleUserOnboarding():
    requiredFieldsForUserOnBoarding = [
        "name",
        "email",
        "sub",
        "user_avatar",
        "workspace_name",
        "board_name",
        "teamMembers",
    ]
    if request.method == "POST":
        dataSentByFrontend = request.get_json()
        for item in requiredFieldsForUserOnBoarding:
            if item not in dataSentByFrontend.keys():
                return jsonify({"message": f"{item} was missing", "status": 400})
        userIdForTheCurrentUser = uuid.uuid4().hex
        workspace_uuid = uuid.uuid4().hex

        modifiedBoardObject = {
            "title": dataSentByFrontend["board_name"],
            "board_uuid": uuid.uuid4().hex,
            "members": [userIdForTheCurrentUser],
            "isPrivate": False,
            "assosiatedWorkspace_uuid": workspace_uuid,
        }

        modifiedWorkspaceObject = {
            "title": dataSentByFrontend["workspace_name"],
            "workspace_uuid": workspace_uuid,
            "members": [userIdForTheCurrentUser],
            "starred": [],
            "userBoards": [modifiedBoardObject],
        }

        # teamMembers = json.loads(dataSentByFrontend["teamMembers"])

        dataSentByFrontend["user_id"] = userIdForTheCurrentUser
        dataSentByFrontend["workspace_details"] = [modifiedWorkspaceObject]
        dataSentByFrontend["starredBoards"] = []
        # dataSentByFrontend["teamMembers"] = teamMembers

        print("final data", dataSentByFrontend)
        try:
            if dataSentByFrontend:
                db["miroUsers"].insert_one(dataSentByFrontend)
                return jsonify({"message": "SUCCESS", "status": 200})

        except Exception as error:
            print(error, "error")
            return jsonify({"message": "FAILURE", "status": 400})


@app.route("/create", methods=["POST"])
def createEitherWorkspaceOR_Board():
    requiredFieldsForCreate = ["title", "type", "userId"]
    if request.method == "POST":
        dataSentByFrontend = request.get_json()
        for item in requiredFieldsForCreate:
            if item not in dataSentByFrontend.keys():
                return jsonify({"message": f"{item} was missing", "status": 400})

        print(dataSentByFrontend, "dataSentByFrontend")

        if dataSentByFrontend["type"] == "workspace":
            modifiedWorkspaceObject = {
                "title": dataSentByFrontend["title"],
                "workspace_uuid": uuid.uuid4().hex,
                "members": [dataSentByFrontend["userId"]],
                "starred": [],
                "userBoards": [],
            }
            try:
                foundUser = db["miroUsers"].find_one(
                    {"user_id": dataSentByFrontend["userId"]}
                )
                if not foundUser:
                    return jsonify({"message": "no user found", "status": 400})
                db["miroUsers"].update_one(
                    {"user_id": dataSentByFrontend["userId"]},
                    {"$push": {"workspace_details": modifiedWorkspaceObject}},
                )
                return jsonify({"message": "SUCCESS", "status": 200})
            except Exception as error:
                print(error, "error")
                return jsonify({"message": "FAILURE", "status": 400})

        elif dataSentByFrontend["type"] == "board":
            # print("in board if blockl")
            modifiedBoardObject = {
                "title": dataSentByFrontend["title"],
                "board_uuid": uuid.uuid4().hex,
                "members": [dataSentByFrontend["userId"]],
                "isPrivate": False,
                "assosiatedWorkspace_uuid": dataSentByFrontend["workspace_uuid"],
                "isStarred": False,
            }
            try:
                # print("in board TRY KA blockl")
                foundUser = db["miroUsers"].find_one(
                    {"user_id": dataSentByFrontend["userId"]}
                )
                if not foundUser:
                    return jsonify({"message": "no user found", "status": 400})

                # Find the corresponding workspace by workspace_uuid
                workspace_index = next(
                    (
                        index
                        for (index, d) in enumerate(foundUser["workspace_details"])
                        if d["workspace_uuid"] == dataSentByFrontend["workspace_uuid"]
                    ),
                    None,
                )

                if workspace_index is None:
                    return jsonify({"message": "Workspace not found", "status": 400})

                # Append the new board object to the userBoards array of the corresponding workspace
                db["miroUsers"].update_one(
                    {
                        "user_id": dataSentByFrontend["userId"],
                        "workspace_details.workspace_uuid": dataSentByFrontend[
                            "workspace_uuid"
                        ],
                    },
                    {"$push": {"workspace_details.$.userBoards": modifiedBoardObject}},
                )

                return jsonify({"message": "SUCCESS", "status": 200})

            except Exception as error:
                print(error, "error")
                return jsonify({"message": "FAILURE", "status": 400})

    return jsonify({"message": "FAILURE", "status": 400})


@app.route("/fetchTeamMembers", methods=["POST"])
def handle_fetching_team_members():
    data = request.get_json()
    logging.info(data)
    if not data.get("board_uuid"):
        return jsonify({"error": "Board UUID missing"}), 400

    user = db["miroUsers"].find_one(
        {"workspace_details.userBoards.board_uuid": data["board_uuid"]}
    )
    if not user:
        return jsonify({"error": "User not found"}), 404
    else:
        for workspace in user["workspace_details"]:
            for board in workspace["userBoards"]:
                if board.get("sharedBoard_id"):
                    try:
                        logging.info(f"DB calling check: {data['board_uuid']}")
                        membersOfSharedBoard = db["sharedBoards"].find_one(
                            {"board_uuid": data["board_uuid"]}
                        )["membersWithMutuallySharedBoards"]
                        if membersOfSharedBoard:
                            return jsonify(membersOfSharedBoard), 200
                    except Exception as err:
                        logging.error(f"Database error for team emmbers: {err}")
                else:
                    return jsonify({"message": "you are the only member"}), 200
        # return jsonify({"error": "Board not found"}), 404
        # if board["board_uuid

    # try:
    #     board_uuid = data["board_uuid"]
    #     result = None
    #     try:
    #         result = db["sharedBoards"].find_one({"board_uuid": board_uuid})
    #     except Exception as err:
    #         logging.error(f"Database error for team emmbers: {err}")

    #     print(result, "result")

    #     if not result:
    #         return jsonify({"error": "Board not found"}), 404
    #     else:
    #         logging.info(result, "result")
    #         return jsonify(result["membersWithMutuallySharedBoards"]), 200

    # except Exception as err:
    #     print(f"Error in fetching team members: {err}")
    #     return jsonify({"error": "Internal server error"}), 500


checkUuidExpiry = {}


@app.route("/generate_Uuid", methods=["POST"])
def generateUuid():
    if request.method == "POST":
        try:
            data = request.get_json()
            validTill = data.get("validTill")  # Extract 'validTill' from JSON data
            # print(validTill, "validTill")
            if not validTill:
                return jsonify({"message": "expiry time missing", "status": 400})

            validTill = int(validTill)
            newUuid = str(uuid.uuid4().hex)
            validityDuration = datetime.now() + timedelta(minutes=validTill)
            checkUuidExpiry[newUuid] = validityDuration
            print(checkUuidExpiry, "object cahce")
            return jsonify({"uuid": newUuid}), 200

        except ValueError:
            return jsonify({"message": "expiry time must be an integer", "status": 400})

        except Exception as err:
            print(err, "err converting valid till time")
            return jsonify({"message": "could not convert time", "status": 400})


@app.route("/validateInviteOnBoarding", methods=["POST"])
def validateInviteProcess():
    data = request.get_json()
    inviteUuid = data["inviteUuid"]
    invitingToSourceUuid = data["invitingToSourceUuid"]
    invitersUuid = data["invitersUuid"]
    inviteToSource = data["inviteToSource"]
    validTill = data["validTill"]

    if (
        not inviteUuid in checkUuidExpiry
    ):  # condition one is that uuid even present in the object
        return jsonify({"message": "invite uuid does not exist", "status": 400})

    userThatInvited = db["miroUsers"].find_one({"user_id": invitersUuid})
    if not userThatInvited:
        return jsonify(
            {"message": "the user that invited you could not be found", "status": 400}
        )

    if inviteUuid in checkUuidExpiry:  # cond2 if it is present is it even validd
        expiryTimeInObject = checkUuidExpiry[inviteUuid]
        if datetime.now() > expiryTimeInObject:
            return jsonify({"message": "uuid has expired", "status": 400})

        else:
            invitersName = userThatInvited["name"]
            if inviteToSource == "workspace":
                allWorkspaces = userThatInvited["workspace_details"]
                fountWorkspace = False
                for i in allWorkspaces:

                    if i["workspace_uuid"] == invitingToSourceUuid:
                        IndividualWorkspaceObject = i
                        fountWorkspace = True
                        break
                if fountWorkspace:
                    return jsonify(
                        {
                            "data": f"title: {IndividualWorkspaceObject['title']} uuid: {IndividualWorkspaceObject['workspace_uuid']} invitersName: {invitersName}",
                            "status": 200,
                        }
                    )
                else:
                    return jsonify(
                        {
                            "message": "no workspace found with the given uuid",
                            "status": 400,
                        }
                    )
            else:
                # if inviteToSource  is board
                invitersName = userThatInvited["name"]
                allWorkspaces = userThatInvited["workspace_details"]
                # print(invitingToSourceUuid, "invitingToSourceUuid")
                found_board = False
                for i in allWorkspaces:
                    for j in i["userBoards"]:
                        if j["board_uuid"] == invitingToSourceUuid:
                            IndividualBoardObject = j
                            found_board = True
                            break  # Exit the inner loop since we found the board
                    if found_board:
                        break  # Exit the outer loop since we found the board

                if found_board:
                    return jsonify(
                        {
                            "data": {
                                "title": IndividualBoardObject["title"],
                                "uuid": IndividualBoardObject["board_uuid"],
                                "invitersName": invitersName,
                            },
                            "status": 200,
                        }
                    )
                else:
                    return jsonify(
                        {"message": "no board found with the given uuid", "status": 400}
                    )

            return jsonify(
                {
                    "data": {
                        "title": IndividualBoardObject["title"],
                        "uuid": IndividualBoardObject["board_uuid"],
                        "invitersName": invitersName,
                    },
                    "status": 200,
                }
            )


@app.route("/AcceptInviedUser", methods=["POST"])
def acceptInvitedUser():
    data = request.get_json()
    logging.info(f"Request data: {data}")

    userIdForTheCurrentUser = uuid.uuid4().hex
    try:
        userThatInvited = db["miroUsers"].find_one({"user_id": data["inviters_Uuid"]})
        logging.info(f"Inviter user: {userThatInvited}")
    except Exception as err:
        logging.error(f"Database error: {err}")

    inviteeAlreadyExists = None
    try:
        inviteeAlreadyExists = db["miroUsers"].find_one({"sub": data["sub"]})

        if inviteeAlreadyExists:
            inviteesUserId = inviteeAlreadyExists["user_id"]
            try:
                boardExitsInSharedCollection = db["sharedBoards"].find_one(
                    {
                        "board_uuid": data["soucre_uuid"],
                    }
                )
                if boardExitsInSharedCollection:
                    try:
                        userIsAlreadyPartOfTheBoard = db["sharedBoards"].find_one(
                            {
                                "$and": [
                                    {
                                        "membersWithMutuallySharedBoards.user_id": inviteesUserId
                                    },
                                    {"board_uuid": data["soucre_uuid"]},
                                ]
                            }
                        )

                        if userIsAlreadyPartOfTheBoard:
                            logging.info(
                                f"board existsssssssssssssssssssssssss {boardExitsInSharedCollection}"
                            )
                            logging.info(
                                f"Userrrrrrrrrrrrrrr is already part of the board: {userIsAlreadyPartOfTheBoard}"
                            )
                            return {"message": "User is already part of the board"}, 400
                    except Exception as err:
                        logging.error(
                            f"Database error for finding user in the shared collection: {err}"
                        )
                        return jsonify({"message": "Database error", "status": 400})
            except Exception as err:
                logging.error(
                    f"Database error for finding board in the shared collection: {err}"
                )
                return jsonify({"message": "Database error", "status": 400})

    except Exception as err:
        logging.error(f"Database error for finding inviteee: {err}")

    if data["InvitedTOWorkspaceOrBoard"] == "board":
        dataOfMutualSharedBoards = {
            "title": data["source_name"],
            "board_uuid": data["soucre_uuid"],
            "membersWithMutuallySharedBoards": [
                # userIdForTheCurrentUser,
                # data["inviters_Uuid"],
                {
                    "name": data["name"],
                    "user_id": (
                        inviteeAlreadyExists["user_id"]
                        if inviteeAlreadyExists
                        else userIdForTheCurrentUser
                    ),
                    "role": "write_access",
                },
                {
                    "name": userThatInvited["name"],
                    "user_id": data["inviters_Uuid"],
                    "role": "master_admin",
                },
            ],
            "isPrivate": False,
            "assosiatedWorkspace_uuid": data["workspace_uuid"],
        }
        modifiedBoardObject = {
            "title": data["source_name"],
            "board_uuid": data["soucre_uuid"],
            "members": [
                (
                    inviteeAlreadyExists["user_id"]
                    if inviteeAlreadyExists
                    else userIdForTheCurrentUser
                )
            ],
            "isPrivate": False,
            "assosiatedWorkspace_uuid": data["workspace_uuid"],
        }

        modifiedWorkspaceObject = {
            "title": data["workspace_name"],
            "workspace_uuid": data["workspace_uuid"],
            "members": [
                (
                    inviteeAlreadyExists["user_id"]
                    if inviteeAlreadyExists
                    else userIdForTheCurrentUser
                )
            ],
            "starred": [],
            "userBoards": [modifiedBoardObject],
        }
        data["starredBoards"] = []
        data["user_id"] = (
            inviteeAlreadyExists["user_id"]
            if inviteeAlreadyExists
            else userIdForTheCurrentUser
        )
        data["workspace_details"] = [modifiedWorkspaceObject]

        try:
            
            boardIsAlreadyMutuallShared = db["sharedBoards"].find_one(
                {"board_uuid": data["soucre_uuid"]}
            )
            shared_board_id = None
            if boardIsAlreadyMutuallShared:
                logging.info("Board already exists in shared collection")
                try:
                    db["sharedBoards"].update_one(
                        {"board_uuid": data["soucre_uuid"]},
                        {
                            "$addToSet": {
                                "membersWithMutuallySharedBoards": {
                                    "name": data["name"],
                                    "user_id": (
                                        inviteeAlreadyExists["user_id"]
                                        if inviteeAlreadyExists
                                        else userIdForTheCurrentUser
                                    ),
                                    "role": "write_access",
                                }
                            }
                        },
                    )
                    # Retrieve the updated document
                    shared_board_id = db["sharedBoards"].find_one(
                        {"board_uuid": data["soucre_uuid"]}
                    )["_id"]

                except Exception as err:
                    logging.error(
                        f"Database error while updating shared collection: {err}"
                    )
            else:
                try:
                    shared_board_id = (
                        db["sharedBoards"]
                        .insert_one(dataOfMutualSharedBoards)
                        .inserted_id
                    )
                except Exception as err:
                    logging.error(
                        f"Database error while inserting into shared collection: {err}"
                    )

            if data:
                if inviteeAlreadyExists:
                    modifiedBoardObject["sharedBoard_id"] = shared_board_id
                    workspaceExists = False  # Flag to track if the workspace exists
                    logging.info(f"Invitee already exists: {inviteeAlreadyExists}")

                    # Iterate over the existing workspace_details to check if current workspace exists
                    for workspace in inviteeAlreadyExists["workspace_details"]:
                        if workspace["workspace_uuid"] == data["workspace_uuid"]:
                            logging.info("Workspace exists matcheeeeeeeeeeeee")
                            # If workspace exists, update it with the new board and set flag to True
                            workspaceExists = True
                            try:
                                logging.info("DB call to update board")
                                # updating the invitee
                                db["miroUsers"].update_one(
                                    {"user_id": inviteeAlreadyExists["user_id"]},
                                    {
                                        "$push": {
                                            "workspace_details.$[outer].userBoards": modifiedBoardObject
                                        }
                                    },
                                    array_filters=[
                                        {"outer.workspace_uuid": data["workspace_uuid"]}
                                    ],
                                )

                                # need to update the inviter as well specially with the shared board id
                                db["miroUsers"].update_one(
                                    {"user_id": data["inviters_Uuid"]},
                                    {
                                        "$set": {
                                            "workspace_details.$[outer].userBoards.$[inner].sharedBoard_id": shared_board_id,
                                            "workspace_details.$[outer].userBoards.$[inner].isPrivate": False,
                                        }
                                    },
                                    array_filters=[
                                        {
                                            "outer.workspace_uuid": data[
                                                "workspace_uuid"
                                            ]
                                        },
                                        {"inner.board_uuid": data["soucre_uuid"]},
                                    ],
                                )

                                return jsonify({"message": "SUCCESS", "status": 200})
                            except Exception as err:
                                logging.error(
                                    f"Database error while inserting into boards collection: {err}"
                                )
                                return jsonify({"message": "FAILURE", "status": 400})
                            # break  # Exit the loop as we've found and updated the existing workspace

                    if not workspaceExists:
                        # If the workspace does not exist, then add it as a new workspace

                        try:
                            logging.info("DB call to insert new workspace with board")
                            # updating the invitee
                            db["miroUsers"].update_one(
                                {"user_id": inviteeAlreadyExists["user_id"]},
                                {
                                    "$push": {
                                        "workspace_details": modifiedWorkspaceObject
                                    }
                                },
                            )
                            # need to update the inviter as well specially with the shared board id
                            db["miroUsers"].update_one(
                                {"user_id": data["inviters_Uuid"]},
                                {
                                    "$set": {
                                        "workspace_details.$[outer].userBoards.$[inner].sharedBoard_id": shared_board_id,
                                        "workspace_details.$[outer].userBoards.$[inner].isPrivate": False,
                                    }
                                },
                                array_filters=[
                                    {"outer.workspace_uuid": data["workspace_uuid"]},
                                    {"inner.board_uuid": data["soucre_uuid"]},
                                ],
                            )
                            return jsonify({"message": "SUCCESS", "status": 200})
                        except Exception as err:
                            logging.error(
                                f"Database error while inserting into user collection: {err}"
                            )
                            return jsonify({"message": "FAILURE", "status": 400})
                else:
                    # updating the invitee i.e inserting his entry
                    modifiedBoardObject["sharedBoard_id"] = shared_board_id
                    logging.info(
                        f"Inviteeeeeeeeeeeeeeee does not exist final board was {modifiedBoardObject}"
                    )
                    try:
                        db["miroUsers"].insert_one(data)
                    except Exception as err:
                        logging.error(
                            f"Database error while inserting into user collection: {err}"
                        )
                    # db["miroUsers"].insert_one(
                    #     data
                    # )  # inserted the new user as his own individual object
                    if not userThatInvited:
                        return jsonify(
                            {
                                "message": "the user that invited you could not be found",
                                "status": 400,
                            }
                        )
                    else:
                        logging.info("Users with mututla boardssssssss")
                        # code is just repeating itself make a function for this 2
                        usersWithMutualBoards = db["miroUsers"].find(
                            {
                                "workspace_details.userBoards.board_uuid": data[
                                    "soucre_uuid"
                                ]
                            }
                        )
                    # updating the inviter no need to loop

                    logging.info(
                        f"Upding the inviter, invitee did not exist: {shared_board_id}"
                    )
                    db["miroUsers"].update_one(
                        {"user_id": data["inviters_Uuid"]},
                        {
                            "$set": {
                                "workspace_details.$[outer].userBoards.$[inner].sharedBoard_id": shared_board_id,
                                "workspace_details.$[outer].userBoards.$[inner].isPrivate": False,
                            }
                        },
                        array_filters=[
                            {"outer.workspace_uuid": data["workspace_uuid"]},
                            {"inner.board_uuid": data["soucre_uuid"]},
                        ],
                    )
                    return jsonify({"message": "SUCCESS", "status": 200})

        except Exception as error:
            logging.error(f"Database operation failed: {error}")
            return jsonify({"message": "FAILURE", "status": 400})

    return jsonify({"message": "FAILURE", "status": 400})


@app.route("/starOrUnStarBoard", methods=["POST"])
def starOrUnStarBoard():
    data = request.get_json()
    logging.info(f"data of frontend for starring: {data}")
    if not data.get("board_uuid"):
        return jsonify({"error": "Board UUID missing"}), 400

    specificBoard = None
    try:
        specificBoard = db["miroUsers"].find_one(
            {"workspace_details.userBoards.board_uuid": data["board_uuid"]}
        )

        logging.info(f"Found board for star it: {specificBoard}")
        if not specificBoard:
            return jsonify({"error": "Board not found"}), 404
        else:
            user = db["miroUsers"].find_one(
                {
                    "user_id": data["user_id"],
                }
            )
            if not user:
                return jsonify({"error": "User not found"}), 404

            else:
                if data["toStarOrUnstar"] == "starIt":
                    try:
                        db["miroUsers"].update_one(
                            {"user_id": data["user_id"]},
                            {
                                "$addToSet": {"starredBoards": data["board_uuid"]},
                            },
                        )
                        logging.info(
                            f"added to array of starred: {data['board_uuid']} and the workspace is {data['workspace_uuid']}"
                        )
                        db["miroUsers"].update_one(
                            {
                                "user_id": data["user_id"],
                                "workspace_details.userBoards": {
                                    "$elemMatch": {
                                        "board_uuid": data["board_uuid"],
                                        "assosiatedWorkspace_uuid": data[
                                            "workspace_uuid"
                                        ],
                                    }
                                },
                            },
                            {
                                "$set": {
                                    "workspace_details.$[outer].userBoards.$[inner].isStarred": data[
                                        "toStarOrUnstar"
                                    ]
                                    == "starIt"
                                }
                            },
                            array_filters=[
                                {"outer.workspace_uuid": data["workspace_uuid"]},
                                {"inner.board_uuid": data["board_uuid"]},
                            ],
                        )

                        logging.info(
                            f"mutated is starred: {data['board_uuid']} and the workspace is {data['workspace_uuid']}"
                        )

                        return jsonify({"message": "Board starred successfully"}), 200
                    except Exception as err:
                        logging.error(
                            f"Database error for finding board to star it 1: {err}"
                        )
                        return jsonify({"error": "Board not found"}), 404

                else:
                    try:
                        db["miroUsers"].update_one(
                            {"user_id": data["user_id"]},
                            {
                                "$pull": {"starredBoards": data["board_uuid"]},
                            },
                        )
                        db["miroUsers"].update_one(
                            {
                                # "user_id": data["user_id"],
                                "workspace_details.userBoards.board_uuid": data[
                                    "board_uuid"
                                ]
                            },
                            {
                                "$set": {
                                    "workspace_details.$[outer].userBoards.$[inner].isStarred": False
                                }
                            },
                            array_filters=[
                                {"outer.workspace_uuid": data["workspace_uuid"]},
                                {"inner.board_uuid": data["board_uuid"]},
                            ],
                        )

                        return jsonify({"message": "Board unstarred successfully"}), 200
                    except Exception as err:
                        logging.error(
                            f"Database error for finding board to star it 2: {err}"
                        )
                        return jsonify({"error": "Board not found"}), 404

    except Exception as err:
        logging.error(f"Database error for finding board to star it 3: {err}")
        if not specificBoard:
            return jsonify({"error": "Board not found"}), 404


@app.route("/fetchFavouriteBoards", methods=["POST"])
def fetchFavouriteBoards():
    data = request.get_json()
    logging.info(f"Data for fetching favourite boards: {data}")
    if not data.get("user_id"):
        return jsonify({"error": "User ID missing"}), 400

    user = db["miroUsers"].find_one({"user_id": data["user_id"]})
    if not user:
        return jsonify({"error": "User not found"}), 404
    else:
        logging.info(
            f"User found for fetching favourite boards11111111111111111111: {user}"
        )
        user["_id"] = str(user["_id"])
        logging.info(f"User found for fetching favourite boards: {user}")
        # return jsonify({"data": user["starredBoards"]}), 200
        try:
            FavouritesboardsData = []
            usersStarredBoards = user["starredBoards"]
            for workspace in user["workspace_details"]:
                for board in workspace["userBoards"]:
                    if board["board_uuid"] in usersStarredBoards:
                        logging.info(
                            f"Board found for fetching favourite boards: {board}"
                        )
                        if "sharedBoard_id" in board:
                            logging.info(f"wtf boards: {board}")
                            board["sharedBoard_id"] = str(board["sharedBoard_id"])
                        FavouritesboardsData.append(board)
            return jsonify({"data": FavouritesboardsData}), 200
        except Exception as err:
            logging.error(f"Database error for fetching favourite boards: {err}")
            return jsonify({"error": "Internal server error"}), 500


@app.route("/removeMemberFromBoard", methods=["POST"])
def removeMemberFromBoard():
    data = request.get_json()
    logging.info(f"Data for removing member from board: {data}")
    if (
        not data.get("board_uuid")
        or not data.get("user_id")
        or not data.get("userThatIsRemoving")
    ):
        return jsonify({"error": "Board UUID or Member ID missing"}), 400

    userThatIsGettingRemoved = None
    try:
        userThatIsGettingRemoved = db["miroUsers"].find_one(
            {"user_id": data["user_id"]}
        )
    except Exception as err:
        logging.error(f"Database error for finding user: {err}")
        return jsonify({"error": "Internal server error"}), 500

    boardFromWhichUserISGettingRemoved = None
    try:
        boardFromWhichUserISGettingRemoved = db["sharedBoards"].find_one(
            {"board_uuid": data["board_uuid"]}
        )
        logging.info(
            f"Board from which user is getting removed: {boardFromWhichUserISGettingRemoved}"
        )

    except Exception as err:
        logging.error(f"Database error for finding board: {err}")
        return jsonify({"error": "Internal server error"}), 500

    # userThatIsGettingRemoved['_id'] = str(userThatIsGettingRemoved['_id'])
    try:
        userThatISRemoving = db["sharedBoards"].find_one(
            {"membersWithMutuallySharedBoards.user_id": data["userThatIsRemoving"]}
        )
        if not userThatISRemoving:
            return jsonify({"error": "User that is removing not found"}), 404
        else:
            userThatISRemoving["_id"] = str(userThatISRemoving["_id"])
            logging.info(
                f"User that is removing**************************: {userThatISRemoving}"
            )
            # userThatIsGettingRemoved['membersWithMutuallySharedBoards'].find({"user_id": data["user_id"]})
            # Inside the loop
            for user in userThatISRemoving["membersWithMutuallySharedBoards"]:
                if user["user_id"] == data["userThatIsRemoving"]:
                    if user["role"] == "master_admin":
                        try:
                            db["sharedBoards"].update_one(
                                {"board_uuid": data["board_uuid"]},
                                {
                                    "$pull": {
                                        "membersWithMutuallySharedBoards": {
                                            "user_id": data["user_id"]
                                        }
                                    }
                                },
                            )
                            logging.info(
                                "Member removed from array of shared collection:"
                            )
                        except Exception as err:
                            logging.error(
                                f"Database error for removing shared board id: {err}"
                            )
                            return jsonify({"error": "Internal server error"}), 500
                    else:
                        return (
                            jsonify(
                                {"error": "Only master admin can remove the member"}
                            ),
                            400,
                        )
                    # Move this outside the loop
        try:

            db["miroUsers"].update_one(
                {
                    "user_id": data["user_id"],
                    "workspace_details.userBoards.board_uuid": data.get("board_uuid"),
                },
                {
                    "$pull": {
                        "workspace_details.$[elem].userBoards": {
                            "board_uuid": data.get("board_uuid")
                        }
                    }
                },
                array_filters=[{"elem.userBoards.board_uuid": data.get("board_uuid")}],
            )

            logging.info("Member removed from array of user collection:")
            return jsonify({"message": "Member removed successfully"}), 200
        except Exception as err:
            logging.error(f"Database error for removing member from board: {err}")
            return jsonify({"error": "Internal server error"}), 500

            # else :
            #     return jsonify({"error": "User not found"}), 404

    except Exception as err:
        logging.error(f"Database error for removing member from board: {err}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/deleteBoard", methods=["POST"])
def deleteBoardWrapper():
    data = request.get_json()
    # email = data['email']
    workspace_uuid = data["workspace_uuid"]
    board_uuid = data["board_uuid"]
    user_id = data["user_id"]
    boardName = data["board_name"]
    isSharred = data.get('isShared')
    user = None
    board = None
    logging.info(f"is sharred variable {isSharred}")

    try:
        if isSharred is None: 
            logging.info(f"in if block {isSharred}")
            specificBoard = None
            specificBoard =  db["sharedBoards"].find_one({"board_uuid": board_uuid})
            if not specificBoard:
                logging.info(f"Board not found in shared collection: {specificBoard}")
                # return jsonify({"error": "Board not found"}), 404
                specificBoard = db["miroUsers"].find_one({"workspace_details.userBoards.board_uuid": board_uuid})
                if not specificBoard:
                    logging.info(f"Board not found in user collection: {specificBoard}")
                    return jsonify({"error": "Board not found"}), 404
                else:
                    logging.info(f"Board found in user collection: {specificBoard}")
                    #pull the board out from the array of userBoards
                    try:
                        db["miroUsers"].update_one(
                            {"user_id": user_id},
                            {
                                "$pull": {
                                    "workspace_details.$[].userBoards": {
                                        "board_uuid": board_uuid
                                    }
                                }
                            },
                        )
                        # repeate code 1
                        boardISStarred = db["miroUsers"].find_one(
                            {"starredBoards": board_uuid}
                        )
                        logging.info(
                            f"Board is starred pre ifffff: {boardISStarred}"
                        )
                        if boardISStarred:
                            db["miroUsers"].update_one(
                                {"starredBoards": board_uuid},
                                {
                                    "$pull": {
                                        "starredBoards": board_uuid
                                    }
                                },
                            )

                        logging.info("Board deleted successfully")
                        return (
                            jsonify(
                                {
                                    "message": "Board deleted successfully"
                                }
                            ),
                            200,
                        )
                    except Exception as err:
                        logging.error(
                            f"Database error for deleting board: {err}"
                        )
                        return (
                            jsonify({"error": "Internal server error for deleting board"}),
                            500,
                        )
                    
            else:
                try:
                    foundUserInSharedCollection = db["sharedBoards"].find_one(
                        {"membersWithMutuallySharedBoards.user_id": user_id}
                    )
                    logging.info(f"Array of members: {foundUserInSharedCollection}")
                    if not foundUserInSharedCollection:
                        return jsonify({"error": "User not found"}), 404
                    else:
                        for user in foundUserInSharedCollection["membersWithMutuallySharedBoards"]:
                            if user["user_id"] == user_id:
                                logging.info(f"User found in shared collection: {user}")
                                if user["role"] == "master_admin":
                                    logging.info("Master admin found")
                                    try:
                                        db["sharedBoards"].delete_one({"board_uuid": board_uuid})

                                        db["miroUsers"].update_many(
                                            {
                                                "workspace_details.userBoards.sharedBoard_id": specificBoard["_id"]
                                            },
                                            {
                                                "$pull": {
                                                    "workspace_details.$[].userBoards": {
                                                        "sharedBoard_id": specificBoard["_id"]
                                                    }
                                                }
                                            },
                                        )
                                        logging.info("Board deleted successfully")
                                        return jsonify({"message": "Board deleted successfully"}), 200
                                    except Exception as err:
                                        logging.error(f"Database error for deleting board: {err}")
                                        return jsonify({"error": "Internal server error for deleting board"}), 500
                                else:
                                    return jsonify({"error": "Only master admin can delete the board"}), 400
                except Exception as err:
                    logging.error(f"Database error for deleting board: {err}")
                    return jsonify({"error": "Internal server error for deleting board"}), 500
        if isSharred == "false":
            logging.info("in if block")
            try:
                user = db["miroUsers"].find_one({"user_id": user_id})
                if not user:
                    return jsonify({"error": "User not found"}), 404
                else:
                    board = db["miroUsers"].find_one(
                        {"workspace_details.userBoards.board_uuid": board_uuid}
                    )
                    logging.info(f"Board found for deleting: {board}")

                    if not board:
                        return jsonify({"error": "Board not found"}), 404
                    else:
                        for workspace in user["workspace_details"]:
                            for board in workspace["userBoards"]:
                                if board["board_uuid"] == board_uuid:
                                    # if board['isPrivate'] == True:
                                    try:
                                        db["miroUsers"].update_one(
                                            {"user_id": user_id},
                                            {
                                                "$pull": {
                                                    "workspace_details.$[].userBoards": {
                                                        "board_uuid": board_uuid
                                                    }
                                                }
                                            },
                                        )
                                        # repeate code 1
                                        boardISStarred = db["miroUsers"].find_one(
                                            {"starredBoards": board_uuid}
                                        )
                                        logging.info(
                                            f"Board is starred pre ifffff: {boardISStarred}"
                                        )
                                        if boardISStarred:
                                            db["miroUsers"].update_one(
                                                {"starredBoards": board_uuid},
                                                {
                                                    "$pull": {
                                                        "starredBoards": board_uuid
                                                    }
                                                },
                                            )

                                        logging.info("Board deleted successfully")
                                        return (
                                            jsonify(
                                                {
                                                    "message": "Board deleted successfully"
                                                }
                                            ),
                                            200,
                                        )
                                    except Exception as err:
                                        logging.error(
                                            f"Database error for deleting board: {err}"
                                        )
                                        return (
                                            jsonify({"error": "Internal server error"}),
                                            500,
                                        )
                                # else:
                                #     return jsonify({"error": "no board found"}), 400

            except Exception as err:
                logging.error(f"not found user for deletin board: {err}")
                return jsonify({"error": "Internal server error"}), 500

        else:
            logging.info("in else block")
            try:
                board = db["sharedBoards"].find_one({"board_uuid": board_uuid})
                if not board:
                    return jsonify({"error": "Board not found"}), 404
                else:
                    try:
                        foundUserInSharedCollection = db["sharedBoards"].find_one(
                            {"membersWithMutuallySharedBoards.user_id": user_id}
                        )
                        logging.info(f"Array of members: {foundUserInSharedCollection}")
                        if not foundUserInSharedCollection:
                            return jsonify({"error": "User not found"}), 404
                        else:

                            for user in foundUserInSharedCollection[
                                "membersWithMutuallySharedBoards"
                            ]:
                                if user["user_id"] == user_id:
                                    logging.info(
                                        f"User found in shared collection: {user}"
                                    )
                                    if user["role"] == "master_admin":
                                        logging.info("Master admin found")
                                        try:
                                            db["sharedBoards"].delete_one(
                                                {"board_uuid": board_uuid}
                                            )

                                            db["miroUsers"].update_many(
                                                {
                                                    "workspace_details.userBoards.sharedBoard_id": board[
                                                        "_id"
                                                    ]
                                                },
                                                {
                                                    "$pull": {
                                                        "workspace_details.$[].userBoards": {
                                                            "sharedBoard_id": board[
                                                                "_id"
                                                            ]
                                                        }
                                                    }
                                                },
                                            )
                                            # repeate code 2
                                            boardISStarred = db["miroUsers"].find_one(
                                                {"starredBoards": board_uuid}
                                            )
                                            logging.info(
                                                f"Board is starred: {boardISStarred}"
                                            )
                                            if boardISStarred:
                                                db["miroUsers"].update_one(
                                                    {"starredBoards": board_uuid},
                                                    {
                                                        "$pull": {
                                                            "starredBoards": board_uuid
                                                        }
                                                    },
                                                )

                                            logging.info("Board deleted successfully")
                                            return (
                                                jsonify(
                                                    {
                                                        "message": "Board deleted successfully"
                                                    }
                                                ),
                                                200,
                                            )
                                        except Exception as err:
                                            logging.error(
                                                f"Database error for deleting board: {err}"
                                            )
                                            return (
                                                jsonify(
                                                    {
                                                        "error": "Internal server error for deleting board"
                                                    }
                                                ),
                                                500,
                                            )
                                    else:
                                        return (
                                            jsonify(
                                                {
                                                    "error": "Only master admin can delete the board"
                                                }
                                            ),
                                            400,
                                        )
                        db["sharedBoards"].delete_one({"board_uuid": board_uuid})
                        logging.info("Board deleted successfully")
                        return jsonify({"message": "Board deleted successfully"}), 200
                    except Exception as err:
                        logging.error(f"Database error for deleting board: {err}")
                        return (
                            jsonify(
                                {"error": "Internal server error for deleting board"}
                            ),
                            500,
                        )
            except Exception as err:
                logging.error(f"Database error for deleting board: {err}")
                return (
                    jsonify({"error": "Internal server error for deleting board"}),
                    500,
                )
    except Exception as err:
        logging.error(f"Database error for deleting board: {err}")
        return jsonify({"error": "Internal server error for deleting board"}), 500


@app.route("/retrieveCanvasState", methods=["POST"])
def retrieveCanvasState():
    data = request.get_json()
    logging.info(f"Data for retrieving canvas state: {data}")
    if not data.get("board_uuid"):
        return jsonify({"error": "Board UUID missing"}), 400
    try:
        board = db["shapes"].find({"boardId": data["board_uuid"]})
        logging.info(f"Board found for retrieving canvas state: {board}")
        if not board:
            return jsonify({"error": "Board not found"}), 404
        else:
            finalShapesArray = []
            for shape in board:
                finalShapesArray.append(shape["shapes"])
            return jsonify({"data": finalShapesArray}), 200
            # emit("doneSending", True)
            # return jsonify({"data": list(board)}), 200
    except Exception as err:
        logging.error(f"Database error for retrieving canvas state: {err}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/uploadImageForEditor', methods=['POST'])
def upload_image():
    logging.info(f'Incoming files: {request.files}')
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    if file:
        result = upload(file) 
        url = result.get('url')
        if url:
            return jsonify({"url": url}), 200
        else:
            return jsonify({"error": "Failed to upload image"}), 500

@app.route("/retrieveTeamMembers", methods=['post'])
def fetchingTeamMembersHandler():
    data = request.get_json()
    logging.info(f"Data for fetching team members: {data}")
    if not data.get("board_uuid"):
        return jsonify({"error": "Board UUID missing"}), 400
    try:
       board = db['sharedBoards'].find_one({"board_uuid": data["board_uuid"]})
       if not board:
        return jsonify({"error": "Board not found"}), 404
       else:
           logging.info(f'memmbersssss {board["membersWithMutuallySharedBoards"]}')
           if(len(board["membersWithMutuallySharedBoards"]) > 0):
               return jsonify({"data": board["membersWithMutuallySharedBoards"]}), 200
           else:
                return jsonify({"error": "No members in array"}), 201
    except Exception as err:
        logging.error(f"Database error for fetching team members: {err}")
        return jsonify({"error": "Internal server error"}), 500


#canvas
user_sessions = {}
@socketio.on("connect")
def handle_connect():
    user_id = request.args.get("user_id")
    if user_id:
        user_sessions[user_id] = request.sid
        print(f"Client {user_id} connected with session {request.sid}")
    else:
        print("No user_id provided on connect")


@socketio.on("readyToUseApp")
def handle_join_board(data):
    boardUuid = data['boardUuid']
    room = f"CanvasState-{boardUuid}"
    join_room(room)
    logging.info(f"Client joined room: {room}")


unique_shape_ids = set()
tempShapesInMemory = []
tempShapesInMemoryForUpdate = []
unique_shape_ids_for_update = set()
delete_queue = []

@socketio.on("addShape")
def handle_add_shape(data):
    global tempShapesInMemory, unique_shape_ids
    shape_id = data['shapes']['id']
    # boardUuid = data['boardUuid']
    room = f"CanvasState-{data['boardId']}"
    logging.info(f"Shape added: {data['shapes']}")

    if shape_id not in unique_shape_ids:
        unique_shape_ids.add(shape_id)
        # join_room(room)
        # emit("shapeAdded", data['shapes'], broadcast=True, include_self=False)
        emit("shapeAdded", data['shapes'], room=room, include_self=False)
        jsonForDb = {
            "shapes": data['shapes'],
            'userId': data['userId'],
            'boardId': data['boardId']
        }
        tempShapesInMemory.append(jsonForDb)
        logging.info(f"Shapes in memory: {tempShapesInMemory}")

        if len(tempShapesInMemory) > 3:
            try:
                db['shapes'].insert_many(tempShapesInMemory)
                tempShapesInMemory = []
                unique_shape_ids.clear()
                logging.info("Shapes in memory cleared after db insertion.")
            except Exception as err:
                logging.error(f"Database error while inserting shapes: {err}")
    else:
        logging.info("Duplicate shape received and ignored.")


@socketio.on("updateShape")
def handle_update_shape(data):
    global tempShapesInMemoryForUpdate
    shape_id = data['shapes']['id']
    room = f"CanvasState-{data['boardId']}"
    logging.info(f"Shape updated: {data['shapes']}")

    # Find if there's already an update pending for this shape in memory.
    existing_update_index = next((i for i, entry in enumerate(tempShapesInMemoryForUpdate) if entry['shapes']['id'] == shape_id), -1)

    if existing_update_index == -1:
        # If no pending update, append to the list.
        logging.info(f"Shape update queued: {data['shapes']}")
        tempShapesInMemoryForUpdate.append({
            "shapes": data['shapes'],
            'userId': data['userId'],
            'boardId': data['boardId']
        })
    else:
        # If there's already a pending update, replace it.
        logging.info(f"Shape update replaced in queue: {data['shapes']}")
        tempShapesInMemoryForUpdate[existing_update_index] = {
            "shapes": data['shapes'],
            'userId': data['userId'],
            'boardId': data['boardId']
        }

    logging.info(f"Shapes in update queue: {tempShapesInMemoryForUpdate}")

    # Process updates in batch or based on some condition, e.g., every few seconds or when the list size reaches a limit.
    if len(tempShapesInMemoryForUpdate) > 3:
        try:
            db["shapes"].bulk_write([
                UpdateOne(
                    {"id": shape["shapes"]["id"]},
                    {"$set": shape["shapes"]},
                    upsert=True
                ) for shape in tempShapesInMemoryForUpdate
            ])
            tempShapesInMemoryForUpdate = []
            logging.info("Shapes in memory cleared after db update.")
        except Exception as err:
            logging.error(f"Database error while updating shapes111111111: {err}")

    
    emit("shapeUpdated", data['shapes'], room=room, include_self=False)

@socketio.on("deleteShape")
def handle_delete_shape(data):
    global delete_queue
    logging.info(f"Shape deleted: {data}")
    room = f"CanvasState-{data['boardId']}"

    delete_queue.append(data['shapes']['id'])
    
    # emit("shapeDeleted", data['shapes']['id'], broadcast=True, include_self=False)
    # join_room(room)
    emit("shapeDeleted", data['shapes']['id'], room=room, include_self=False)

    # Process the delete queue if it has more than 3 items
    if len(delete_queue) > 3:
        flush_delete_queue()

def flush_delete_queue():
    global delete_queue
    if not delete_queue:
        return

    try:
        db['shapes'].delete_many({"shapes.id": {"$in": delete_queue}})
        logging.info(f"Deleted {len(delete_queue)} shapes from database.")
        delete_queue = []  # Clear the queue after processing
    except Exception as err:
        logging.error(f"Database error while deleting shapes: {err}")

# @socketio.on("cursorMove")
# def handle_cursor_move(data):
#     logging.info(f'cursor data {data}')
#     emit("cursorMoved", data, broadcast=True, include_self=True)

def perdoicDbUpdate():
    global user_sessions, tempShapesInMemory, tempShapesInMemoryForUpdate, delete_queue
    while True:
            # logging.info("Periodic DB update started")
            
            # Check for active user sessions
            if not user_sessions:
                # logging.info("No user sessions found")
                time.sleep(5)  
                continue 
            
            if tempShapesInMemory:
                logging.info('Periodic DB update for adding shapes')
                try:
                    db["shapes"].insert_many(tempShapesInMemory)
                    tempShapesInMemory = []
                    logging.info("Shapes in memory cleared after db insertion.")
                except Exception as err:
                    logging.error(f"Database error while inserting shapes: {err}")
            
            if tempShapesInMemoryForUpdate:
                logging.info('Periodic DB update for updating shapes')
                try:
                    db["shapes"].bulk_write([
                        UpdateOne(
                            {"id": shape['shapes']["id"]},
                            {"$set": shape['shapes']},
                            upsert=True
                        ) for shape in tempShapesInMemoryForUpdate
                    ])
                    tempShapesInMemoryForUpdate = []
                    logging.info("Shapes in memory cleared after db update.")
                except Exception as err:
                    logging.error(f"Database error while updating shapes222222: {err}")

            flush_delete_queue()
            
            time.sleep(5) 

thread = threading.Thread(target=perdoicDbUpdate)
thread.start()


#notion editor
update_buffer = {}
buffer_lock = threading.Lock()

UPDATE_INTERVAL = 10
@socketio.on("editorUpdate")
def handleEditorUpdated(data):
    logging.info(f"Editor updated: {data}")
    room = f"CanvasState-{data['board_uuid']}"
    with buffer_lock:
        if data['board_uuid'] not in update_buffer:
            update_buffer[data['board_uuid']] = []
        update_buffer[data['board_uuid']].append(data)
    emit('editorUpdated', data, room=room, include_self=False)



@app.route("/retrieveEditorData", methods=['POST'])
def handleRetrieveEditorData():
    board_uuid = request.get_json().get("board_uuid")
    logging.info(f"Retrieving editor data for board: {board_uuid}")
    try:
        editor_data = db["editorData"].find({"board_uuid": board_uuid})
        logging.info(f"Editor data found: {editor_data}")
        if not editor_data:
            return jsonify({"error": "Editor data not found"}), 404
        arrayOfEditorData = []
        for data in editor_data:

            data["_id"] = str(data["_id"])
            arrayOfEditorData.append(data)
        logging.info(f"Array of editor data: {arrayOfEditorData}")
        return jsonify({"data": arrayOfEditorData}), 200
    except Exception as err:
        logging.error(f"Database error for retrieving editor data: {err}")
        return jsonify({"error": "Internal server error"}), 500
    #     return jsonify({"data": list(editor_data)}), 200
    # except Exception as err:
    #     logging.error(f"Database error for retrieving editor data: {err}")
    #     return jsonify({"error": "Internal server error"}), 500

@socketio.on("editorCleared")
def handleEditorCleared(data):
    logging.info(f"Editor cleared: {data}")
    room = f"CanvasState-{data['board_uuid']}"
    with buffer_lock:
        update_buffer[data['board_uuid']] = []
        try:
            editor_collection.delete_many({"board_uuid": data['board_uuid']})
            logging.info(f"Editor data cleared for board: {data['board_uuid']}")
        except Exception as err:
            logging.error(f"Database error while clearing editor data: {err}")
    emit('ClearedEditor', data, room=room, include_self=False)

@socketio.on("imageDeleted")
def handleRemoveImage(data):
    logging.info(f"Image deleted: {data}")
    emit('deletedImage', data, broadcast=True, include_self=False)


def save_updates_to_db():
    while True:
        time.sleep(UPDATE_INTERVAL)
        # logging.info(f"Periodic DB update started for editor data {update_buffer}")
        with buffer_lock:
            if update_buffer:
                for board_uuid, updates in update_buffer.items():
                    for update in updates:
                        logging.info(f"Saving update to DB: {update}")
                        query = {'id': update['editorData']['id'], 'board_uuid': board_uuid}
                        new_data = {
                            'id': update['editorData']['id'],
                            'board_uuid': board_uuid,
                            'block_index': update.get('blockIndex'),
                            'type': update['editorData']['type'],
                            'props': update['editorData']['props'],
                            'content': update['editorData']['content'],
                            'children': update['editorData'].get('children', [])
                        }
                        editor_collection.update_one(query, {'$set': new_data}, upsert=True)
                update_buffer.clear()
            # else:
            #     logging.info("No updates to save to DB")

# Start the background task
threading.Thread(target=save_updates_to_db, daemon=True).start()



#calling
@socketio.on('make_call')
def make_call(data):
    # user_sessions.pop("undefined")
    # del user_sessions['undefined']
    caller_username = data['caller_username']
    userIds = data['userIds']
    room = f'testRoom {data["roomTokenString"]}'
    roomToken = data['roomTokenString']
    logging.info(f"room token for the call: {roomToken}")
    logging.info(f"caller id {data['calerId']}")
    logging.info(f"Making call to users {userIds} in sesions object{user_sessions}")
    callerid = data['calerId']
    for userId in userIds:
        if userId['id'] in user_sessions:
            join_room(room, sid=user_sessions[userId['id']])
        else:
            print(f"No session found for user {userId}")
    
    emit('incoming_call', {'caller_username': caller_username, "roomTokenString": roomToken, 'caller_id': data['calerId']}, room=room, broadcast=True, include_self=False)

@socketio.on('accept_call')
def accept_call(data):
    user_id = data['userId']
    caller_id = data['caller_id']
    logging.info(f"token when acceptiung from notification {data['roomTokenString']}")
    roomToken = data['roomTokenString']
    room = f'finalRoom {roomToken}'
    
    if user_id in user_sessions and caller_id in user_sessions:
        join_room(room, sid=user_sessions[user_id])
        join_room(room, sid=user_sessions[caller_id])
        emit('call_accepted', {'user_id': user_id, 'caller_id': caller_id, "roomTokenString": roomToken}, room=room)
    else:
        missing_ids = [uid for uid in [user_id, caller_id] if uid not in user_sessions]
        print(f"Session IDs missing for {missing_ids}")


@socketio.on("decline_call")
def handle_declinedCall(data):
    # room = "finalRoom"
    roomToken = data['roomTokenString']
    room = f"finalRoom {roomToken}"
    user_id = data["userId"]
    caller_id = data['caller_id']
    name = data['name']
    if user_id in user_sessions and caller_id in user_sessions:
        emit("call_declined", {"name": name}, room=f'testRoom {roomToken}', broadcast=True, include_self=False)
        leave_room(room, sid=user_sessions[user_id])
        leave_room(room, sid=user_sessions[caller_id])
        leave_room(f'testRoom {roomToken}', sid=user_sessions[user_id])
        leave_room(f'testRoom {roomToken}', sid=user_sessions[caller_id])

    logging.info(f"User {user_id} declined to join room {room}")
    logging.info(f"final state of rooms post leaving {rooms()}")
    # Handle any additional logic for declining the call, like notifying the caller


@socketio.on("disconnect")
def handle_disconnect():
    session_id = request.sid
    user_id = None
    for uid, sid in user_sessions.items():
        if sid == session_id:
            user_id = uid
            break
    if user_id:
        del user_sessions[user_id]
        logging.info(f"Client {user_id} disconnected and session {session_id} removed")
    else:
        logging.warning(f"Session {session_id} disconnected but no matching user_id found")

if __name__ == "__main__":
    app.run(debug=True, port=5000)
