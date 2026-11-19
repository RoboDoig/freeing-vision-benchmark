using System;
using System.ComponentModel;
using System.Globalization;
using System.Reactive.Linq;
using Bonsai;
using OpenCV.Net;
using OpenTK;

namespace UclOpenFreeingVisionBenchmark
{
    /// <summary>
    /// Specifies the axis convention of the camera frame that a <see cref="RigidFit"/> was computed in.
    /// </summary>
    public enum CameraAxisConvention
    {
        /// <summary>
        /// x right, y up, z towards the viewer (the camera looks down -z). This is the frame produced by
        /// Bonsai.Aruco MarkerViewMatrix / Bonsai.Shaders ExtrinsicsTransform.
        /// </summary>
        OpenGL,

        /// <summary>x right, y down, z forward (the camera looks down +z), as used by OpenCV solvePnP.</summary>
        OpenCV
    }

    /// <summary>
    /// The result of projecting an image point onto the calibrated arena plane.
    /// </summary>
    public class PlaneProjection
    {
        /// <summary>
        /// The input point in undistorted, normalised pinhole coordinates (x_n, y_n), OpenCV convention.
        /// </summary>
        public Point2f NormalizedPoint { get; set; }

        /// <summary>
        /// The 3D position of the point in the camera frame (same axis convention and units as the fit).
        /// </summary>
        public Vector3d CameraPosition { get; set; }

        /// <summary>
        /// The position of the point in the arena (plane) frame: X and Y relative to the arena/grid origin
        /// (marker 0 centre), Z equal to the projection height.
        /// </summary>
        public Vector3d PlanePosition { get; set; }

        /// <summary>
        /// False if the input point was not finite (e.g. no blob detected), was not in normalised coordinates,
        /// or if its camera ray does not hit the plane in front of the camera. Positions are NaN when invalid.
        /// </summary>
        public bool Valid { get; set; }

        public override string ToString()
        {
            return string.Format(CultureInfo.InvariantCulture,
                "PlaneProjection(Plane=({0:G4}, {1:G4}), Camera=({2:G4}, {3:G4}, {4:G4}), Valid={5})",
                PlanePosition.X, PlanePosition.Y, CameraPosition.X, CameraPosition.Y, CameraPosition.Z, Valid);
        }
    }

    /// <summary>
    /// Projects undistorted, normalised image points onto the arena plane given by a <see cref="RigidFit"/>,
    /// by intersecting each point's camera ray with the plane at height <see cref="Height"/> above the arena
    /// surface.
    /// </summary>
    /// <remarks>
    /// The input is a pair of (normalised point, fit), e.g. from WithLatestFrom(normalised centroid, ArenaFit).
    /// Produce the normalised point with Bonsai.Vision UndistortPoints, configured with the camera intrinsics
    /// and with ImageSize left unset: in that mode it outputs normalised pinhole coordinates
    /// (equivalent to cv::undistortPoints without a new projection matrix). Raw or undistorted pixel
    /// coordinates are not valid input. The fit must come from the same camera, and <see cref="Convention"/>
    /// must match the frame the fit was computed in.
    /// </remarks>
    [Combinator]
    [Description("Projects normalised image points (from UndistortPoints) onto the calibrated arena plane, returning arena and camera-frame 3D positions.")]
    [WorkflowElementCategory(ElementCategory.Transform)]
    public class ProjectToPlane
    {
        // Normalised coordinates beyond this correspond to rays > ~84 degrees off-axis: almost certainly pixels.
        const double MaxNormalizedCoordinate = 10.0;

        [Description("Height of the tracked point above the arena surface, in the units of the fit (e.g. metres). Zero for points on the surface.")]
        public double Height { get; set; }

        [Description("The axis convention of the camera frame the fit was computed in. OpenGL for Bonsai.Aruco / ExtrinsicsTransform output.")]
        public CameraAxisConvention Convention { get; set; }

        public IObservable<PlaneProjection> Process(IObservable<Tuple<Point2f, RigidFit>> source)
        {
            return Observable.Defer(() =>
            {
                var height = Height;
                var convention = Convention;
                return source.Select(input => Project(input.Item1, input.Item2, height, convention));
            });
        }

        internal static PlaneProjection Project(Point2f normalized, RigidFit fit, double height, CameraAxisConvention convention)
        {
            var nan = new Vector3d(double.NaN, double.NaN, double.NaN);
            var result = new PlaneProjection { NormalizedPoint = normalized, CameraPosition = nan, PlanePosition = nan };
            if (fit == null || float.IsNaN(normalized.X) || float.IsNaN(normalized.Y) ||
                float.IsInfinity(normalized.X) || float.IsInfinity(normalized.Y) ||
                Math.Abs(normalized.X) > MaxNormalizedCoordinate || Math.Abs(normalized.Y) > MaxNormalizedCoordinate)
            {
                return result;
            }

            // Camera ray through the point. Normalised coordinates are in OpenCV convention (y down, z forward).
            var ray = convention == CameraAxisConvention.OpenGL
                ? new Vector3d(normalized.X, -normalized.Y, -1.0)
                : new Vector3d(normalized.X, normalized.Y, 1.0);

            // Plane at the given height: passes through t + h*n with normal n. Ray from the camera centre: s * ray.
            var normal = fit.Normal;
            var pointOnPlane = fit.Translation + height * normal;
            var denominator = Vector3d.Dot(normal, ray);
            if (Math.Abs(denominator) < 1e-12) return result;
            var s = Vector3d.Dot(normal, pointOnPlane) / denominator;
            if (s <= 0) return result; // intersection behind the camera

            var cameraPosition = s * ray;
            result.CameraPosition = cameraPosition;
            result.PlanePosition = fit.ToReference(cameraPosition);
            result.Valid = true;
            return result;
        }
    }
}
