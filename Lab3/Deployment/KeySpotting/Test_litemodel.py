import tensorflow as tf
from Microphone import Mic
import numpy as np

sensor = Mic(1,48000,16)

sensor.Record('./','record_0.wav')

'''
input_data = tf.constant(x,dtype=tf.float32)
input_data = tf.expand_dims(input_data, 0)

interpreter = tf.lite.Interpreter(model_path='model_tflite')
interpreter.allocate_tensors()

input_details = interpreter.get_input_details()
output_details = interpreter.get_output_details()

interpreter.set_tensor(input_details[0]['index'], input_data)
interpreter.invoke()
my_output = interpreter.get_tensor(output_details[0]['index'])[0]

print(f'Measured: {y[0]}, {y[1]} --- Predicted: {my_output[0]:.2f}, {my_output[1]:.2f} --- MAE: {np.abs(y[0] - my_output[0]):.2f}, {np.abs(y[1] - my_output[1]):.2f}')

'''