from __future__ import print_function
import argparse
import random # to set the python random seed
import numpy # to set the numpy random seed
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torchvision import datasets, transforms
# Ignore excessive warnings
import logging
logging.propagate = False 
logging.getLogger().setLevel(logging.ERROR)

# WandB – Import the wandb library
import wandb
os.environ["WANDB_API_KEY"] = 'f9b4b72764ed69d483d5ffea9479c4db9924c95a'
os.environ["WANDB_MODE"] = "online"

# WandB – Login to your wandb account so you can log all your metrics
# init project use the api key to fill into authorize field.
wandb login

class Net(nn.Module):
    def __init__(self):
        super(Net, self).__init__()
        
        # Conv2d() adds a convolution layer that generates 2 dimensional feature maps to learn different aspects of our image
        self.conv1 = nn.Conv2d(3, 6, kernel_size=5)
        self.conv2 = nn.Conv2d(6, 16, kernel_size=5)
        
        # Linear(x,y) creates dense, fully connected layers with x inputs and y outputs
        # Linear layers simply output the dot product of our inputs and weights.
        self.fc1 = nn.Linear(16 * 5 * 5, 120)
        self.fc2 = nn.Linear(120, 84)
        self.fc3 = nn.Linear(84, 10)

    def forward(self, x):
        x = F.relu(F.max_pool2d(self.conv1(x), 2))
        x = F.relu(F.max_pool2d(self.conv2(x), 2))
        
        # Reshapes x into size (-1, 16 * 5 * 5) so we can feed the convolution layer outputs into our fully connected layer
        x = x.view(-1, 16 * 5 * 5)
        
        # We apply the relu activation function and dropout to the output of our fully connected layers
        x = F.relu(self.fc1(x))
        x = F.relu(self.fc2(x))
        x = self.fc3(x)
        
        # Finally we apply the softmax function to squash the probabilities of each class (0-9) and ensure they add to 1.
        return F.log_softmax(x, dim=1)


def train(args, model, device, train_loader, optimizer, epoch):
    # Switch model to training mode. This is necessary for layers like dropout, batchnorm etc which behave differently in training and evaluation mode
    model.train()
    
    # We loop over the data iterator, and feed the inputs to the network and adjust the weights.
    for batch_idx, (data, target) in enumerate(train_loader):
        if batch_idx > 20:
          break
        # Load the input features and labels from the training dataset
        data, target = data.to(device), target.to(device)
        
        # Reset the gradients to 0 for all learnable weight parameters
        optimizer.zero_grad()
        
        # Forward pass: Pass image data from training dataset, make predictions about class image belongs to (0-9 in this case)
        output = model(data)
        
        # Define our loss function, and compute the loss
        loss = F.nll_loss(output, target)
        
        # Backward pass: compute the gradients of the loss w.r.t. the model's parameters
        loss.backward()
        
        # Update the neural network weights
        optimizer.step()


def test(args, model, device, test_loader, classes):
    model.eval()
    test_loss = 0
    correct = 0

    example_images = []
    with torch.no_grad():
        for data, target in test_loader:
            # Load the input features and labels from the test dataset
            data, target = data.to(device), target.to(device)
            
            # Make predictions: Pass image data from test dataset, make predictions about class image belongs to (0-9 in this case)
            output = model(data)
            
            # Compute the loss sum up batch loss
            test_loss += F.nll_loss(output, target, reduction='sum').item()
            
            # Get the index of the max log-probability
            pred = output.max(1, keepdim=True)[1]
            correct += pred.eq(target.view_as(pred)).sum().item()
            
            # WandB – Log images in your test dataset automatically, along with predicted and true labels by passing pytorch tensors with image data into wandb.Image
            example_images.append(wandb.Image(
                data[0], caption="Pred: {} Truth: {}".format(classes[pred[0].item()], classes[target[0]])))
    
    # WandB – wandb.log(a_dict) logs the keys and values of the dictionary passed in and associates the values with a step.
    wandb.log({
        "Examples": example_images,
        "Test Accuracy": 100. * correct / len(test_loader.dataset),
        "Test Loss": test_loss})


# WandB – Initialize a new run
wandb.init(project="wandb", entity="tucnguyenvan")
wandb.watch_called = False # Re-run the model without restarting the runtime, unnecessary after our next release

# WandB – Config is a variable that holds and saves hyperparameters and inputs
config = wandb.config
config.lr = 0.1
config.epochs=50
config.batch_size = 4
config.test_batch_size = 10
config.momentum = 0.1
config.no_cuda = False
config.seed = 42
config.log_interval = 10


def main():
    use_cuda = not config.no_cuda and torch.cuda.is_available()
    device = torch.device("cuda" if use_cuda else "cpu")
    kwargs = {'num_workers': 1, 'pin_memory': True} if use_cuda else {}

    torch.manual_seed(config.seed) # pytorch random seed
    torch.backends.cudnn.deterministic = True

    # Load the dataset: We're training our CNN on CIFAR10 (https://www.cs.toronto.edu/~kriz/cifar.html)
    # First we define the tranformations to apply to our images
    transform = transforms.Compose(
    [transforms.ToTensor(),
     transforms.Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5))])
    
    # Now we load our training and test datasets and apply the transformations defined above
    train_loader = torch.utils.data.DataLoader(datasets.CIFAR10(root='./data', train=True,
                                              download=True, transform=transform), batch_size=config.batch_size,
                                              shuffle=True, **kwargs)
    test_loader = torch.utils.data.DataLoader(datasets.CIFAR10(root='./data', train=False,
                                             download=True, transform=transform), batch_size=config.test_batch_size,
                                             shuffle=False, **kwargs)

    classes = ('plane', 'car', 'bird', 'cat',
               'deer', 'dog', 'frog', 'horse', 'ship', 'truck')

    # Initialize our model, recursively go over all modules and convert their parameters and buffers to CUDA tensors (if device is set to cuda)
    model = Net().to(device)
    optimizer = optim.SGD(model.parameters(), lr=config.lr,
                          momentum=config.momentum)
    
    # WandB – wandb.watch() automatically fetches all layer dimensions, gradients, model parameters and logs them automatically to your dashboard.
    # Using log="all" log histograms of parameter values in addition to gradients
    wandb.watch(model, log="all")

    for epoch in range(1, config.epochs + 1):
        train(config, model, device, train_loader, optimizer, epoch)
        test(config, model, device, test_loader, classes)

if __name__ == '__main__':
    main()