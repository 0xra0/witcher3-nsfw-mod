// Pose probe for the retargeted sex cutscene. On by default (no console needed);
// bpose() toggles it. While a cutscene plays, shows every 2 s where the engine put both actors:
//   d = her pelvis - Geralt's pelvis, in Geralt's entity frame (x right, y fwd, z up)
//   r = her entity root - Geralt's entity root, same frame; h = her heading - his
// Compare against the same numbers measured in Blender.

@addField(CR4Player)
var brothelPoseOff : bool;

@addField(CR4Player)
var brothelPoseClock : float;

@addField(CR4Player)
var brothelPoseT : float;

@wrapMethod(CR4Player) function OnSpawned(spawnData : SEntitySpawnData)
{
	wrappedMethod(spawnData);
	AddTimer('BrothelPoseTimer', 0.25, true);
}

exec function bpose()
{
	var player : CR4Player;

	player = (CR4Player)thePlayer;
	player.brothelPoseOff = !player.brothelPoseOff;
	if (!player.brothelPoseOff)
		BDiag_Show("pose probe on");
	else
		BDiag_Show("pose probe off");
}

function BrothelPoseLocal(v : Vector, heading : float) : string
{
	var c, s, x, y : float;

	c = CosF(Deg2Rad(heading));
	s = SinF(Deg2Rad(heading));
	// W3 heading 0 faces +Y; rotate the world offset into the actor's frame.
	x = v.X * c + v.Y * s;
	y = -v.X * s + v.Y * c;
	return "(" + FloatToStringPrec(x, 2) + "," + FloatToStringPrec(y, 2) + "," + FloatToStringPrec(v.Z, 2) + ")";
}

@addMethod(CR4Player)
timer function BrothelPoseTimer(dt : float, id : int)
{
	var her : CActor;
	var gh : float;
	var gp, hp, gr, hr : Vector;

	if (brothelPoseOff || !theGame.IsDialogOrCutscenePlaying() || brothelLocked.Size() == 0)
	{
		brothelPoseClock = 0;
		brothelPoseT = 0;
		return;
	}
	brothelPoseT += dt;
	brothelPoseClock += dt;
	if (brothelPoseClock < 2.0)
		return;
	brothelPoseClock = 0;

	her = brothelLocked[0];
	if (!her)
		return;
	gh = GetHeading();
	gp = GetBoneWorldPosition('pelvis');
	hp = her.GetBoneWorldPosition('pelvis');
	// .Z only works on a variable, not on a call's return value.
	gr = GetWorldPosition();
	hr = her.GetWorldPosition();
	// queue=false: replace the previous readout instead of queueing 15 s
	// notifications behind it (the queue made every reading stale).
	theGame.GetGuiManager().ShowNotification("t=" + FloatToStringPrec(brothelPoseT, 0)
		+ " d=" + BrothelPoseLocal(hp - gp, gh)
		+ " r=" + BrothelPoseLocal(hr - gr, gh)
		+ " h=" + FloatToStringPrec(AngleDistance(her.GetHeading(), gh), 0)
		+ " gz=" + FloatToStringPrec(gp.Z - gr.Z, 2)
		+ " hz=" + FloatToStringPrec(hp.Z - hr.Z, 2), 2500.0, false);
}
